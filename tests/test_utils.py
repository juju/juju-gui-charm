#!/usr/bin/env python2

from contextlib import contextmanager
import os
import shutil
from simplejson import dumps
import tempfile
import tempita
import unittest

import charmhelpers
from utils import (
    _get_by_attr,
    API_PORT,
    cmd_log,
    first_path_in_dir,
    get_release_file_url,
    get_zookeeper_address,
    JUJU_GUI_DIR,
    JUJU_PEM,
    parse_source,
    render_to_file,
    save_or_create_certificates,
    start_agent,
    start_gui,
    start_improv,
    stop,
    WEB_PORT,
)
# Import the whole utils package for monkey patching.
import utils


class AttrDict(dict):
    """A dict with the ability to access keys as attributes."""

    def __getattr__(self, attr):
        if attr in self:
            return self[attr]
        raise AttributeError


class AttrDictTest(unittest.TestCase):

    def test_key_as_attribute(self):
        # Ensure attributes can be used to retrieve dict values.
        attr_dict = AttrDict(myattr='myvalue')
        self.assertEqual('myvalue', attr_dict.myattr)

    def test_attribute_not_found(self):
        # An AttributeError is raised if the dict does not contain an attribute
        # corresponding to an existent key.
        with self.assertRaises(AttributeError):
            AttrDict().myattr


class FirstPathInDirTest(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory)
        self.path = os.path.join(self.directory, 'file_or_dir')

    def test_file_path(self):
        # Ensure the full path of a file is correctly returned.
        open(self.path, 'w').close()
        self.assertEqual(self.path, first_path_in_dir(self.directory))

    def test_directory_path(self):
        # Ensure the full path of a directory is correctly returned.
        os.mkdir(self.path)
        self.assertEqual(self.path, first_path_in_dir(self.directory))

    def test_empty_directory(self):
        # An IndexError is raised if the directory is empty.
        self.assertRaises(IndexError, first_path_in_dir, self.directory)


def make_collection(attr, values):
    """Create a collection of objects having an attribute named *attr*.

    The value of the *attr* attribute, for each instance, is taken from
    the *values* sequence.
    """
    return [AttrDict({attr: value}) for value in values]


class MakeCollectionTest(unittest.TestCase):

    def test_factory(self):
        # Ensure the factory returns the expected object instances.
        instances = make_collection('myattr', range(5))
        self.assertEqual(5, len(instances))
        for num, instance in enumerate(instances):
            self.assertEqual(num, instance.myattr)


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


class FileStub(object):
    """Simulate a Launchpad hosted file returned by launchpadlib."""

    def __init__(self, file_link):
        self.file_link = file_link

    def __str__(self):
        return self.file_link


class GetReleaseFileUrlTest(unittest.TestCase):

    project = AttrDict(
        series=(
            AttrDict(
                name='stable',
                releases=(
                    AttrDict(
                        version='0.1.1',
                        files=(
                            FileStub('http://example.com/0.1.1.dmg'),
                            FileStub('http://example.com/0.1.1.tgz'),
                        ),
                    ),
                    AttrDict(
                        version='0.1.0',
                        files=(
                            FileStub('http://example.com/0.1.0.dmg'),
                            FileStub('http://example.com/0.1.0.tgz'),
                        ),
                    ),
                ),
            ),
            AttrDict(
                name='trunk',
                releases=(
                    AttrDict(
                        version='0.1.1+build.1',
                        files=(
                            FileStub('http://example.com/0.1.1+build.1.dmg'),
                            FileStub('http://example.com/0.1.1+build.1.tgz'),
                        ),
                    ),
                    AttrDict(
                        version='0.1.0+build.1',
                        files=(
                            FileStub('http://example.com/0.1.0+build.1.dmg'),
                            FileStub('http://example.com/0.1.0+build.1.tgz'),
                        ),
                    ),
                ),
            ),
        ),
    )

    def test_latest_stable_release(self):
        # Ensure the correct URL is returned for the latest stable release.
        url = get_release_file_url(self.project, 'stable', None)
        self.assertEqual('http://example.com/0.1.1.tgz', url)

    def test_latest_trunk_release(self):
        # Ensure the correct URL is returned for the latest trunk release.
        url = get_release_file_url(self.project, 'trunk', None)
        self.assertEqual('http://example.com/0.1.1+build.1.tgz', url)

    def test_specific_stable_release(self):
        # Ensure the correct URL is returned for a specific version of the
        # stable release.
        url = get_release_file_url(self.project, 'stable', '0.1.0')
        self.assertEqual('http://example.com/0.1.0.tgz', url)

    def test_specific_trunk_release(self):
        # Ensure the correct URL is returned for a specific version of the
        # trunk release.
        url = get_release_file_url(self.project, 'trunk', '0.1.0+build.1')
        self.assertEqual('http://example.com/0.1.0+build.1.tgz', url)

    def test_series_not_found(self):
        # A ValueError is raised if the series cannot be found.
        with self.assertRaises(ValueError) as cm:
            get_release_file_url(self.project, 'unstable', None)
        self.assertIn('series not found', str(cm.exception))

    def test_no_releases(self):
        # A ValueError is raised if the series does not contain releases.
        project = AttrDict(series=[AttrDict(name='stable', releases=[])])
        with self.assertRaises(ValueError) as cm:
            get_release_file_url(project, 'stable', None)
        self.assertIn('series does not contain releases', str(cm.exception))

    def test_release_not_found(self):
        # A ValueError is raised if the release cannot be found.
        with self.assertRaises(ValueError) as cm:
            get_release_file_url(self.project, 'stable', '2.0')
        self.assertIn('release not found', str(cm.exception))

    def test_file_not_found(self):
        # A ValueError is raised if the hosted file cannot be found.
        project = AttrDict(
            series=[
                AttrDict(
                    name='stable',
                    releases=[AttrDict(version='0.1.0', files=[])],
                ),
            ],
        )
        with self.assertRaises(ValueError) as cm:
            get_release_file_url(project, 'stable', None)
        self.assertIn('file not found', str(cm.exception))

    def test_file_not_found_in_latest_release(self):
        # The URL of a file from a previous release is returned if the latest
        # one does not contain tarballs.
        project = AttrDict(
            series=[
                AttrDict(
                    name='stable',
                    releases=[
                        AttrDict(version='0.1.1', files=[]),
                        AttrDict(
                            version='0.1.0',
                            files=[FileStub('http://example.com/0.1.0.tgz')],
                        ),
                    ],
                ),
            ],
        )
        url = get_release_file_url(project, 'stable', None)
        self.assertEqual('http://example.com/0.1.0.tgz', url)


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
        expected = ('trunk', '0.1.0+build.1')
        self.assertTupleEqual(expected, parse_source('0.1.0+build.1'))

    def test_bzr_branch(self):
        # Ensure a Bazaar branch is correctly parsed.
        sources = ('lp:example', 'http://bazaar.launchpad.net/example')
        for source in sources:
            self.assertTupleEqual(('branch', source), parse_source(source))


class RenderToFileTest(unittest.TestCase):

    def setUp(self):
        self.destination_file = tempfile.NamedTemporaryFile()
        self.addCleanup(self.destination_file.close)
        self.template = tempita.Template('{{foo}}, {{bar}}')
        with tempfile.NamedTemporaryFile(delete=False) as template_file:
            template_file.write(self.template.content)
            self.template_path = template_file.name
        self.addCleanup(os.remove, self.template_path)

    def test_render_to_file(self):
        # Ensure the template is correctly rendered using the given context.
        context = {'foo': 'spam', 'bar': 'eggs'}
        render_to_file(self.template_path, context, self.destination_file.name)
        expected = self.template.substitute(context)
        self.assertEqual(expected, self.destination_file.read())


class SaveOrCreateCertificatesTest(unittest.TestCase):

    def setUp(self):
        base_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base_dir)
        self.cert_path = os.path.join(base_dir, 'certificates')
        self.cert_file = os.path.join(self.cert_path, 'juju.crt')
        self.key_file = os.path.join(self.cert_path, 'juju.key')

    def test_generation(self):
        # Ensure certificates are correctly generated.
        save_or_create_certificates(
            self.cert_path, 'some ignored contents', None)
        self.assertIn('CERTIFICATE', open(self.cert_file).read())
        self.assertIn('PRIVATE KEY', open(self.key_file).read())

    def test_provided_certificates(self):
        # Ensure files are correctly saved if their contents are provided.
        save_or_create_certificates(self.cert_path, 'mycert', 'mykey')
        self.assertIn('mycert', open(self.cert_file).read())
        self.assertIn('mykey', open(self.key_file).read())

    def test_pem_file(self):
        # Ensure the pem file is created concatenating the key and cert files.
        save_or_create_certificates(self.cert_path, 'Certificate', 'Key')
        pem_file = os.path.join(self.cert_path, JUJU_PEM)
        self.assertEqual('KeyCertificate', open(pem_file).read())


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
        self.ssl_cert_path = 'ssl/cert/path'

    def tearDown(self):
        # Undo all of the monkey patching.
        for fn, fcns in self.functions.items():
            setattr(utils, fn, fcns[0])
        charmhelpers.command = self.command

    def test_start_improv(self):
        staging_env = 'large'
        start_improv(
            staging_env, self.ssl_cert_path, self.destination_file.name)
        conf = self.destination_file.read()
        self.assertTrue('--port %s' % API_PORT in conf)
        self.assertTrue(staging_env + '.json' in conf)
        self.assertTrue(self.ssl_cert_path in conf)
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['juju-api-improv'])
        self.assertEqual(self.actions, [charmhelpers.START])

    def test_start_agent(self):
        start_agent(self.ssl_cert_path, self.destination_file.name)
        conf = self.destination_file.read()
        self.assertTrue('--port %s' % API_PORT in conf)
        self.assertTrue('JUJU_ZOOKEEPER=%s' % self.fake_zk_address in conf)
        self.assertTrue(self.ssl_cert_path in conf)
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['juju-api-agent'])
        self.assertEqual(self.actions, [charmhelpers.START])

    def test_start_gui(self):
        config_js_file = self.destination_file
        haproxy_file = tempfile.NamedTemporaryFile()
        self.addCleanup(haproxy_file.close)
        nginx_file = tempfile.NamedTemporaryFile()
        self.addCleanup(nginx_file.close)
        ssl_cert_path = '/tmp/certificates/'
        start_gui(
            False, 'This is login help.', True, True, ssl_cert_path, True,
            haproxy_path=haproxy_file.name, nginx_path=nginx_file.name,
            config_js_path=config_js_file.name)
        self.assertEqual(self.svc_ctl_call_count, 2)
        self.assertEqual(self.service_names, ['nginx', 'haproxy'])
        self.assertEqual(self.actions, [charmhelpers.START] * 2)
        haproxy_conf = haproxy_file.read()
        self.assertIn('ca-base {0}'.format(ssl_cert_path), haproxy_conf)
        self.assertIn('crt-base {0}'.format(ssl_cert_path), haproxy_conf)
        self.assertIn('ws1 127.0.0.1:{0}'.format(API_PORT), haproxy_conf)
        self.assertIn('web1 127.0.0.1:{0}'.format(WEB_PORT), haproxy_conf)
        self.assertIn('ca-file {0}'.format(JUJU_PEM), haproxy_conf)
        self.assertIn('crt {0}'.format(JUJU_PEM), haproxy_conf)
        js_conf = config_js_file.read()
        self.assertIn('consoleEnabled: false', js_conf)
        self.assertIn('user: "admin"', js_conf)
        self.assertIn('password: "admin"', js_conf)
        self.assertIn('login_help: "This is login help."', js_conf)
        self.assertIn('readOnly: true', js_conf)
        nginx_conf = nginx_file.read()
        self.assertIn('juju-gui/build-', nginx_conf)
        self.assertIn('listen 127.0.0.1:{0}'.format(WEB_PORT), nginx_conf)
        self.assertIn('alias {0}/test/;'.format(JUJU_GUI_DIR), nginx_conf)

    def test_stop_staging(self):
        stop(True)
        self.assertEqual(self.svc_ctl_call_count, 3)
        self.assertEqual(
            self.service_names, ['haproxy', 'nginx', 'juju-api-improv'])
        self.assertEqual(self.actions, [charmhelpers.STOP] * 3)

    def test_stop_production(self):
        stop(False)
        self.assertEqual(self.svc_ctl_call_count, 3)
        self.assertEqual(
            self.service_names, ['haproxy', 'nginx', 'juju-api-agent'])
        self.assertEqual(self.actions, [charmhelpers.STOP] * 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
