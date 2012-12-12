#!/usr/bin/env python2

from contextlib import contextmanager
import os
import tempfile
import unittest
import charmhelpers
from simplejson import dumps

from utils import (
    cmd_log,
    get_zookeeper_address,
    render_to_file,
    start_improv
)
# Import the whole utils package for monkey patching.
import utils

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


class StartImprovTest(unittest.TestCase):

    def setUp(self):
        self.service_name = None
        self.action = None
        self.svc_ctl_called = False
        # Monkey patches.
        def service_control_mock(service_name, action):
            self.svc_ctl_called = True
            self.service_name = service_name
            self.action = action
        def noop(*args):
            pass
        @contextmanager
        def su(user):
            yield None

        self.functions = dict(
            service_control=(utils.service_control, service_control_mock),
            log=(utils.log, noop),
            su=(utils.su, su),
            )
        # Apply the patches.
        for fn,fcns in self.functions.items():
            setattr(utils, fn, fcns[1])

        self.destination_file = tempfile.NamedTemporaryFile()
        self.addCleanup(self.destination_file.close)

        def tearDown(self):
            # Undo all of the monkey patching.
            for fn,fcns in self.functions.items():
                setattr(utils, fn, fcns[0])

    def test_start(self):
        port = '1234'
        staging_env = 'large'
        start_improv(port, staging_env, self.destination_file.name)
        conf = self.destination_file.read()
        self.assertTrue('--port %s' % port in conf)
        self.assertTrue(staging_env + '.json' in conf)
        self.assertTrue(self.svc_ctl_called)
        self.assertEqual(self.service_name, 'juju-api-improv')
        self.assertEqual(self.action, charmhelpers.START)

if __name__ == '__main__':
    unittest.main(verbosity=2)
