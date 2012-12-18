#!/usr/bin/env python2

from collections import namedtuple
from contextlib import contextmanager
import os
from simplejson import dumps
import tempfile
import unittest

import charmhelpers
from utils import (
    _get_by_attr,
    cmd_log,
    get_zookeeper_address,
    parse_source,
    render_to_file,
    start_agent,
    start_gui,
    start_improv,
    stop,
)
# Import the whole utils package for monkey patching.
import utils


def make_collection(attr, values):
    """Create a collection of objects having an attribute named *attr*.

    The value of the *attr* attribute, for each instance, is taken from
    the *values* sequence.
    """
    Item = namedtuple('Item', [attr])
    return [Item(value) for value in values]


class GetByAttrTest(unittest.TestCase):

    attr = 'myattr'
    collection = make_collection(attr, range(5))

    def test_item_found(self):
        # Ensure an object instance is correctly returned if found in
        # the collection.
        item = _get_by_attr(self.collection, self.attr, 3)
        self.assertEqual(3, item.myattr)

    def test_value_not_found(self):
        # None is returned if the collection does not contain the requested
        # item.
        item = _get_by_attr(self.collection, self.attr, '__does_not_exist__')
        self.assertIsNone(item)

    def test_attr_not_found(self):
        # An AttributeError is raised if items in collection does not have the
        # required attribute.
        with self.assertRaises(AttributeError):
            _get_by_attr(self.collection, 'another_attr', 0)


class GetReleaseFileUrlTest(unittest.TestCase):

    # TODO.
    pass


class GetZookeeperAddressTest(unittest.TestCase):

    def setUp(self):
        self.zookeeper_address = 'example.com:2000'
        contents = 'env JUJU_ZOOKEEPER="{0}"\n'.format(self.zookeeper_address)
        with tempfile.NamedTemporaryFile(delete=False) as agent_file:
            agent_file.write(contents)
            self.agent_file_path = agent_file.name
        self.addCleanup(os.remove, self.agent_file_path)

    def test_get_zookeeper_address(self):
        # Ensure the Zookeeper address is correctly retreived.
        address = get_zookeeper_address(self.agent_file_path)
        self.assertEqual(self.zookeeper_address, address)


class ParseSourceTest(unittest.TestCase):

    def test_latest_stable_release(self):
        # Ensure the latest stable release is correctly parsed.
        expected = ('stable', None)
        self.assertTupleEqual(expected, parse_source('stable'))

    def test_latest_trunk_release(self):
        # Ensure the latest trunk release is correctly parsed.
        expected = ('trunk', None)
        self.assertTupleEqual(expected, parse_source('trunk'))

    def test_stable_release(self):
        # Ensure a specific stable release is correctly parsed.
        expected = ('stable', '0.1.0')
        self.assertTupleEqual(expected, parse_source('0.1.0'))

    def test_trunk_release(self):
        # Ensure a specific trunk release is correctly parsed.
        expected = ('trunk', '0.1.0build1')
        self.assertTupleEqual(expected, parse_source('0.1.0build1'))

    def test_bzr_branch(self):
        # Ensure a Bazaar branch is correctly parsed.
        sources = ('lp:example', 'bzr+ssh://bazaar.launchpad.net/example')
        for source in sources:
            self.assertTupleEqual(('branch', source), parse_source(source))


class RenderToFileTest(unittest.TestCase):

    def setUp(self):
        self.destination_file = tempfile.NamedTemporaryFile()
        self.addCleanup(self.destination_file.close)
        self.template_contents = '%(foo)s, %(bar)s'
        with tempfile.NamedTemporaryFile(delete=False) as template_file:
            template_file.write(self.template_contents)
            self.template_path = template_file.name
        self.addCleanup(os.remove, self.template_path)

    def test_render_to_file(self):
        # Ensure the template is correctly rendered using the given context.
        context = {'foo': 'spam', 'bar': 'eggs'}
        render_to_file(self.template_path, context, self.destination_file.name)
        expected = self.template_contents % context
        self.assertEqual(expected, self.destination_file.read())


class CmdLogTest(unittest.TestCase):
    def setUp(self):
        # Patch the charmhelpers 'command', which powers get_config.  The
        # result of this is the mock_config dictionary will be returned.
        # The monkey patch is undone in the tearDown.
        self.command = charmhelpers.command
        fd, self.log_file_name = tempfile.mkstemp()
        os.close(fd)
        mock_config = {'command-log-file': self.log_file_name}
        charmhelpers.command = lambda *args: lambda: dumps(mock_config)

    def tearDown(self):
        charmhelpers.command = self.command

    def test_contents_logged(self):
        cmd_log('foo')
        line = open(self.log_file_name, 'r').read()
        self.assertTrue(line.endswith(': juju-gui@INFO \nfoo\n'))


class StartStopTest(unittest.TestCase):

    def setUp(self):
        self.service_names = []
        self.actions = []
        self.svc_ctl_call_count = 0
        self.fake_zk_address = '192.168.5.26'
        # Monkey patches.
        self.command = charmhelpers.command

        def service_control_mock(service_name, action):
            self.svc_ctl_call_count += 1
            self.service_names.append(service_name)
            self.actions.append(action)

        def noop(*args):
            pass

        @contextmanager
        def su(user):
            yield None

        def get_zookeeper_address_mock(fp):
            return self.fake_zk_address

        self.functions = dict(
            service_control=(utils.service_control, service_control_mock),
            log=(utils.log, noop),
            su=(utils.su, su),
            run=(utils.run, noop),
            unit_get=(utils.unit_get, noop),
            get_zookeeper_address=(
                utils.get_zookeeper_address, get_zookeeper_address_mock)
            )
        # Apply the patches.
        for fn, fcns in self.functions.items():
            setattr(utils, fn, fcns[1])

        self.destination_file = tempfile.NamedTemporaryFile()
        self.addCleanup(self.destination_file.close)

    def tearDown(self):
        # Undo all of the monkey patching.
        for fn, fcns in self.functions.items():
            setattr(utils, fn, fcns[0])
        charmhelpers.command = self.command

    def test_start_improv(self):
        port = '1234'
        staging_env = 'large'
        start_improv(port, staging_env, self.destination_file.name)
        conf = self.destination_file.read()
        self.assertTrue('--port %s' % port in conf)
        self.assertTrue(staging_env + '.json' in conf)
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['juju-api-improv'])
        self.assertEqual(self.actions, [charmhelpers.START])

    def test_start_agent(self):
        port = '1234'
        start_agent(port, self.destination_file.name)
        conf = self.destination_file.read()
        self.assertTrue('--port %s' % port in conf)
        self.assertTrue('JUJU_ZOOKEEPER=%s' % self.fake_zk_address in conf)
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['juju-api-agent'])
        self.assertEqual(self.actions, [charmhelpers.START])

    def test_start_gui(self):
        port = '1234'
        nginx_file = tempfile.NamedTemporaryFile()
        self.addCleanup(nginx_file.close)
        config_js_file = tempfile.NamedTemporaryFile()
        self.addCleanup(config_js_file.close)
        start_gui(port, False, True, self.destination_file.name,
                  nginx_file.name, config_js_file.name)
        conf = self.destination_file.read()
        self.assertTrue('/usr/sbin/nginx' in conf)
        nginx_conf = nginx_file.read()
        self.assertTrue('juju-gui/build-debug' in nginx_conf)
        self.assertEqual(self.svc_ctl_call_count, 2)
        self.assertEqual(self.service_names, ['nginx', 'juju-gui'])
        self.assertEqual(self.actions, [charmhelpers.STOP, charmhelpers.START])

    def test_stop_staging(self):
        mock_config = {'staging': True}
        charmhelpers.command = lambda *args: lambda: dumps(mock_config)
        stop()
        self.assertEqual(self.svc_ctl_call_count, 2)
        self.assertEqual(self.service_names, ['juju-gui', 'juju-api-improv'])
        self.assertEqual(self.actions, [charmhelpers.STOP, charmhelpers.STOP])

    def test_stop_production(self):
        mock_config = {'staging': False}
        charmhelpers.command = lambda *args: lambda: dumps(mock_config)
        stop()
        self.assertEqual(self.svc_ctl_call_count, 2)
        self.assertEqual(self.service_names, ['juju-gui', 'juju-api-agent'])
        self.assertEqual(self.actions, [charmhelpers.STOP, charmhelpers.STOP])


if __name__ == '__main__':
    unittest.main(verbosity=2)
