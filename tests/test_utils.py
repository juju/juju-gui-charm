# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2012-2013 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Juju GUI utils tests."""

from contextlib import contextmanager
import json
import os
import shutil
from subprocess import CalledProcessError
import tempfile
import unittest

import charmhelpers
from shelltoolbox import environ
import tempita
import yaml

from utils import (
    API_PORT,
    JUJU_GUI_DIR,
    JUJU_PEM,
    WEB_PORT,
    _get_by_attr,
    cmd_log,
    compute_build_dir,
    first_path_in_dir,
    get_api_address,
    get_release_file_url,
    get_zookeeper_address,
    legacy_juju,
    log_hook,
    parse_source,
    get_npm_cache_archive_url,
    install_builtin_server,
    install_tornado,
    remove_apache_setup,
    remove_haproxy_setup,
    render_to_file,
    save_or_create_certificates,
    setup_apache_config,
    setup_haproxy_config,
    start_agent,
    start_builtin_server,
    start_haproxy_apache,
    start_improv,
    stop_agent,
    stop_builtin_server,
    stop_haproxy_apache,
    stop_improv,
    write_builtin_server_startup,
    write_gui_config,
)
# Import the whole utils package for monkey patching.
import utils


class AttrDict(dict):
    """A dict with the ability to access keys as attributes."""

    def __getattr__(self, attr):
        try:
            return self[attr]
        except KeyError:
            raise AttributeError


class TestAttrDict(unittest.TestCase):

    def test_key_as_attribute(self):
        # Ensure attributes can be used to retrieve dict values.
        attr_dict = AttrDict(myattr='myvalue')
        self.assertEqual('myvalue', attr_dict.myattr)

    def test_attribute_not_found(self):
        # An AttributeError is raised if the dict does not contain an attribute
        # corresponding to an existent key.
        with self.assertRaises(AttributeError):
            AttrDict().myattr


class TestFirstPathInDir(unittest.TestCase):

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


class TestGetApiAddress(unittest.TestCase):

    env_address = 'env.example.com:17070'
    agent_address = 'agent.example.com:17070'

    @contextmanager
    def agent_file(self, addresses=None):
        """Set up a directory structure similar to the one created by juju.

        If addresses are provided, also create a machiner directory and an
        agent file containing the addresses.
        Remove the directory structure when exiting from the context manager.
        """
        base_dir = tempfile.mkdtemp()
        unit_dir = tempfile.mkdtemp(dir=base_dir)
        machine_dir = os.path.join(base_dir, 'machine-1')
        if addresses is not None:
            os.mkdir(machine_dir)
            with open(os.path.join(machine_dir, 'agent.conf'), 'w') as conf:
                yaml.dump({'apiinfo': {'addrs': addresses}}, conf)
        try:
            yield unit_dir, machine_dir
        finally:
            shutil.rmtree(base_dir)

    def test_retrieving_address_from_env(self):
        # The API address is correctly retrieved from the environment.
        with environ(JUJU_API_ADDRESSES=self.env_address):
            self.assertEqual(self.env_address, get_api_address())

    def test_multiple_addresses_in_env(self):
        # If multiple API addresses are listed in the environment variable,
        # the first one is returned.
        addresses = '{} foo.example.com:42'.format(self.env_address)
        with environ(JUJU_API_ADDRESSES=addresses):
            self.assertEqual(self.env_address, get_api_address())

    def test_both_env_and_agent_file(self):
        # If the API address is included in both the environment and the
        # agent.conf file, the environment variable takes precedence.
        with environ(JUJU_API_ADDRESSES=self.env_address):
            with self.agent_file([self.agent_address]) as (unit_dir, _):
                self.assertEqual(self.env_address, get_api_address(unit_dir))

    def test_retrieving_address_from_agent_file(self):
        # The API address is correctly retrieved from the machiner agent file.
        with self.agent_file([self.agent_address]) as (unit_dir, _):
            self.assertEqual(self.agent_address, get_api_address(unit_dir))

    def test_multiple_addresses_in_agent_file(self):
        # If multiple API addresses are listed in the agent file, the first
        # one is returned.
        addresses = [self.agent_address, 'foo.example.com:42']
        with self.agent_file(addresses) as (unit_dir, _):
            self.assertEqual(self.agent_address, get_api_address(unit_dir))

    def test_missing_env_and_agent_file(self):
        # An IOError is raised if the agent configuration file is not found.
        with self.agent_file() as (unit_dir, machine_dir):
            os.mkdir(machine_dir)
            self.assertRaises(IOError, get_api_address, unit_dir)

    def test_missing_env_and_agent_directory(self):
        # An IOError is raised if the machine directory is not found.
        with self.agent_file() as (unit_dir, _):
            self.assertRaises(IOError, get_api_address, unit_dir)


class TestLegacyJuju(unittest.TestCase):

    def setUp(self):
        self.base_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base_dir)
        # Monkey patch utils.CURRENT_DIR.
        self.original_current_dir = utils.CURRENT_DIR
        utils.CURRENT_DIR = tempfile.mkdtemp(dir=self.base_dir)

    def tearDown(self):
        # Restore the original utils.CURRENT_DIR.
        utils.CURRENT_DIR = self.original_current_dir

    def test_jujucore(self):
        # If the agent file is found this is a juju-core environment.
        agent_path = os.path.join(self.base_dir, 'agent.conf')
        open(agent_path, 'w').close()
        self.assertFalse(legacy_juju())

    def test_pyjuju(self):
        # If the agent file does not exist this is a PyJuju environment.
        self.assertTrue(legacy_juju())


def make_collection(attr, values):
    """Create a collection of objects having an attribute named *attr*.

    The value of the *attr* attribute, for each instance, is taken from
    the *values* sequence.
    """
    return [AttrDict({attr: value}) for value in values]


class TestMakeCollection(unittest.TestCase):

    def test_factory(self):
        # Ensure the factory returns the expected object instances.
        instances = make_collection('myattr', range(5))
        self.assertEqual(5, len(instances))
        for num, instance in enumerate(instances):
            self.assertEqual(num, instance.myattr)


class TestGetByAttr(unittest.TestCase):

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


class TestGetReleaseFileUrl(unittest.TestCase):

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


class TestGetZookeeperAddress(unittest.TestCase):

    def setUp(self):
        self.zookeeper_address = 'example.com:2000'
        contents = 'env JUJU_ZOOKEEPER="{}"\n'.format(self.zookeeper_address)
        with tempfile.NamedTemporaryFile(delete=False) as agent_file:
            agent_file.write(contents)
            self.agent_file_path = agent_file.name
        self.addCleanup(os.remove, self.agent_file_path)

    def test_get_zookeeper_address(self):
        # Ensure the Zookeeper address is correctly retreived.
        address = get_zookeeper_address(self.agent_file_path)
        self.assertEqual(self.zookeeper_address, address)


class TestLogHook(unittest.TestCase):

    def setUp(self):
        # Monkeypatch the charmhelpers log function.
        self.output = []
        self.original = utils.log
        utils.log = self.output.append

    def tearDown(self):
        # Restore the original charmhelpers log function.
        utils.log = self.original

    def test_logging(self):
        # The function emits log messages on entering and exiting the hook.
        with log_hook():
            self.output.append('executing hook')
        self.assertEqual(3, len(self.output))
        enter_message, executing_message, exit_message = self.output
        self.assertIn('>>> Entering', enter_message)
        self.assertEqual('executing hook', executing_message)
        self.assertIn('<<< Exiting', exit_message)

    def test_subprocess_error(self):
        # If a CalledProcessError exception is raised, the command output is
        # logged.
        with self.assertRaises(CalledProcessError) as cm:
            with log_hook():
                raise CalledProcessError(2, 'command', 'output')
        exception = cm.exception
        self.assertIsInstance(exception, CalledProcessError)
        self.assertEqual(2, exception.returncode)
        self.assertEqual('output', self.output[-2])

    def test_error(self):
        # Possible errors are re-raised by the context manager.
        with self.assertRaises(TypeError) as cm:
            with log_hook():
                raise TypeError
        exception = cm.exception
        self.assertIsInstance(exception, TypeError)
        self.assertIn('<<< Exiting', self.output[-1])


class TestParseSource(unittest.TestCase):

    def setUp(self):
        # Monkey patch utils.CURRENT_DIR.
        self.original_current_dir = utils.CURRENT_DIR
        utils.CURRENT_DIR = '/current/dir'

    def tearDown(self):
        # Restore the original utils.CURRENT_DIR.
        utils.CURRENT_DIR = self.original_current_dir

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
            expected = ('branch', (source, None))
            self.assertEqual(expected, parse_source(source))

    def test_bzr_branch_and_revision(self):
        # A Bazaar branch is correctly parsed when including revision.
        sources = ('lp:example:42', 'http://bazaar.launchpad.net/example:1')
        for source in sources:
            expected = ('branch', tuple(source.rsplit(':', 1)))
            self.assertEqual(expected, parse_source(source))

    def test_url(self):
        expected = ('url', 'http://example.com/gui')
        self.assertTupleEqual(
            expected, parse_source('url:http://example.com/gui'))

    def test_file_url(self):
        expected = ('url', 'file:///foo/bar')
        self.assertTupleEqual(expected, parse_source('url:/foo/bar'))

    def test_relative_file_url(self):
        expected = ('url', 'file:///current/dir/foo/bar')
        self.assertTupleEqual(expected, parse_source('url:foo/bar'))


class TestRenderToFile(unittest.TestCase):

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


class TestSaveOrCreateCertificates(unittest.TestCase):

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


class TestCmdLog(unittest.TestCase):

    def setUp(self):
        # Patch the charmhelpers 'command', which powers get_config.  The
        # result of this is the mock_config dictionary will be returned.
        # The monkey patch is undone in the tearDown.
        self.command = charmhelpers.command
        fd, self.log_file_name = tempfile.mkstemp()
        os.close(fd)
        mock_config = {'command-log-file': self.log_file_name}
        charmhelpers.command = lambda *args: lambda: json.dumps(mock_config)

    def tearDown(self):
        charmhelpers.command = self.command

    def test_contents_logged(self):
        cmd_log('foo')
        line = open(self.log_file_name, 'r').read()
        self.assertTrue(line.endswith(': juju-gui@INFO \nfoo\n'))


class TestStartImprovAgentGui(unittest.TestCase):

    def setUp(self):
        self.service_names = []
        self.actions = []
        self.svc_ctl_call_count = 0
        self.run_call_count = 0
        self.fake_zk_address = '192.168.5.26'
        self.build_dir = 'juju-gui/build-'
        self.charmworld_url = 'http://charmworld.example'
        self.ssl_cert_path = 'ssl/cert/path'

        # Monkey patches.

        def service_control_mock(service_name, action):
            self.svc_ctl_call_count += 1
            self.service_names.append(service_name)
            self.actions.append(action)

        def noop(*args):
            pass

        def run(*args):
            self.run_call_count += 1

        @contextmanager
        def su(user):
            yield None

        def get_zookeeper_address_mock(fp):
            return self.fake_zk_address

        self.files = {}
        orig_rtf = utils.render_to_file

        def render_to_file(template, context, dest):
            target = tempfile.NamedTemporaryFile()
            orig_rtf(template, context, target.name)
            with open(target.name, 'r') as fp:
                self.files[os.path.basename(dest)] = fp.read()

        self.utils_names = dict(
            service_control=(utils.service_control, service_control_mock),
            log=(utils.log, noop),
            su=(utils.su, su),
            run=(utils.run, run),
            unit_get=(utils.unit_get, noop),
            render_to_file=(utils.render_to_file, render_to_file),
            get_zookeeper_address=(
                utils.get_zookeeper_address, get_zookeeper_address_mock),
            get_api_address=(utils.get_api_address, noop),
            APACHE_PORTS=(utils.APACHE_PORTS, 'PORTS_NOT_THERE'),
            APACHE_SITE=(utils.APACHE_SITE, 'SITE_NOT_THERE'),
        )
        # Apply the patches.
        for fn, fcns in self.utils_names.items():
            setattr(utils, fn, fcns[1])

        self.shutil_copy = shutil.copy
        shutil.copy = noop

    def tearDown(self):
        # Undo all of the monkey patching.
        for fn, fcns in self.utils_names.items():
            setattr(utils, fn, fcns[0])
        shutil.copy = self.shutil_copy

    def test_start_improv(self):
        staging_env = 'large'
        start_improv(staging_env, self.ssl_cert_path,)
        conf = self.files['juju-api-improv.conf']
        self.assertTrue('--port %s' % API_PORT in conf)
        self.assertTrue(staging_env + '.json' in conf)
        self.assertTrue(self.ssl_cert_path in conf)
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['juju-api-improv'])
        self.assertEqual(self.actions, [charmhelpers.START])

    def test_stop_improv(self):
        stop_improv()
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['juju-api-improv'])
        self.assertEqual(self.actions, [charmhelpers.STOP])

    def test_start_agent(self):
        start_agent(self.ssl_cert_path, 'config')
        conf = self.files['juju-api-agent.conf']
        self.assertTrue('--port %s' % API_PORT in conf)
        self.assertTrue('JUJU_ZOOKEEPER=%s' % self.fake_zk_address in conf)
        self.assertTrue(self.ssl_cert_path in conf)
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['juju-api-agent'])
        self.assertEqual(self.actions, [charmhelpers.START])

    def test_stop_agent(self):
        stop_agent()
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['juju-api-agent'])
        self.assertEqual(self.actions, [charmhelpers.STOP])

    def test_compute_build_dir(self):
        for (in_staging, serve_tests, result) in (
            (False, False, 'build-prod'),
            (True, False, 'build-debug'),
            (False, True, 'build-prod'),
            (True, True, 'build-prod'),
        ):
            build_dir = compute_build_dir(in_staging, serve_tests)
            self.assertIn(
                result, build_dir, 'in_staging: {}, serve_tests: {}'.format(
                    in_staging, serve_tests))

    def test_setup_haproxy_config(self):
        setup_haproxy_config(self.ssl_cert_path)
        haproxy_conf = self.files['haproxy.cfg']
        self.assertIn('ca-base {}'.format(self.ssl_cert_path), haproxy_conf)
        self.assertIn('crt-base {}'.format(self.ssl_cert_path), haproxy_conf)
        self.assertIn('ws1 127.0.0.1:{}'.format(API_PORT), haproxy_conf)
        self.assertIn('web1 127.0.0.1:{}'.format(WEB_PORT), haproxy_conf)
        self.assertIn('ca-file {}'.format(JUJU_PEM), haproxy_conf)
        self.assertIn('crt {}'.format(JUJU_PEM), haproxy_conf)
        self.assertIn('redirect scheme https', haproxy_conf)

    def test_remove_haproxy_setup(self):
        remove_haproxy_setup()
        self.assertEqual(self.run_call_count, 2)

    def test_setup_apache_config(self):
        setup_apache_config(self.build_dir, serve_tests=True)
        apache_site_conf = self.files['SITE_NOT_THERE']
        self.assertIn('juju-gui/build-', apache_site_conf)
        self.assertIn('VirtualHost *:{}'.format(WEB_PORT), apache_site_conf)
        self.assertIn(
            'Alias /test {}/test/'.format(JUJU_GUI_DIR), apache_site_conf)
        apache_ports_conf = self.files['PORTS_NOT_THERE']
        self.assertIn('NameVirtualHost *:8000', apache_ports_conf)
        self.assertIn('Listen 8000', apache_ports_conf)

    def test_remove_apache_setup(self):
        remove_apache_setup()
        self.assertEqual(self.run_call_count, 3)

    def test_start_haproxy_apache(self):
        start_haproxy_apache(JUJU_GUI_DIR, False, self.ssl_cert_path, True)
        self.assertEqual(self.svc_ctl_call_count, 2)
        self.assertEqual(self.service_names, ['apache2', 'haproxy'])
        self.assertEqual(
            self.actions, [charmhelpers.RESTART, charmhelpers.RESTART])

    def test_stop_haproxy_apache(self):
        stop_haproxy_apache()
        self.assertEqual(self.svc_ctl_call_count, 2)
        self.assertEqual(self.service_names, ['haproxy', 'apache2'])
        self.assertEqual(self.actions, [charmhelpers.STOP, charmhelpers.STOP])

    def test_install_tornado(self):
        install_tornado()
        self.assertEqual(self.run_call_count, 1)

    def test_install_builtin_server(self):
        install_builtin_server()
        self.assertEqual(self.run_call_count, 1)

    def test_write_builtin_server_startup(self):
        write_builtin_server_startup(
            JUJU_GUI_DIR, self.ssl_cert_path, serve_tests=True, insecure=True)
        guiserver_conf = self.files['guiserver.conf']
        self.assertIn('description "GUIServer"', guiserver_conf)
        self.assertIn('--apiurl="ws://127.0.0.1:8080"', guiserver_conf)
        self.assertIn('--apiversion="python"', guiserver_conf)
        self.assertIn('--servetests', guiserver_conf)
        self.assertIn('--insecure', guiserver_conf)

    def test_start_builtin_server(self):
        start_builtin_server(
            JUJU_GUI_DIR, self.ssl_cert_path, False, insecure=False)
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['guiserver'])
        self.assertEqual(self.actions, [charmhelpers.RESTART])

    def test_stop_builtin_server(self):
        stop_builtin_server()
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['guiserver'])
        self.assertEqual(self.actions, [charmhelpers.STOP])
        self.assertEqual(self.run_call_count, 1)

    def test_write_gui_config(self):
        write_gui_config(
            False, 'This is login help.', True, True, self.charmworld_url,
            self.build_dir, use_analytics=True, config_js_path='config')
        js_conf = self.files['config']
        self.assertIn('consoleEnabled: false', js_conf)
        self.assertIn('user: "admin"', js_conf)
        self.assertIn('password: "admin"', js_conf)
        self.assertIn('login_help: "This is login help."', js_conf)
        self.assertIn('readOnly: true', js_conf)
        self.assertIn("socket_url: 'wss://", js_conf)
        self.assertIn('socket_protocol: "wss"', js_conf)
        self.assertIn('charmworldURL: "http://charmworld.example"', js_conf)
        self.assertIn('useAnalytics: true', js_conf)

    def test_write_gui_config_insecure(self):
        write_gui_config(
            False, 'This is login help.', True, True, self.charmworld_url,
            self.build_dir, secure=False, config_js_path='config')
        js_conf = self.files['config']
        self.assertIn("socket_url: 'ws://", js_conf)
        self.assertIn('socket_protocol: "ws"', js_conf)

    def test_setup_haproxy_config_insecure(self):
        setup_haproxy_config(self.ssl_cert_path, secure=False)
        # The insecure approach eliminates the https redirect.
        self.assertNotIn('redirect scheme https', self.files['haproxy.cfg'])

    def test_write_gui_config_sandbox(self):
        write_gui_config(
            False, 'This is login help.', False, False, self.charmworld_url,
            self.build_dir, sandbox=True, config_js_path='config')
        js_conf = self.files['config']
        self.assertIn('sandbox: true', js_conf)
        self.assertIn('user: "admin"', js_conf)
        self.assertIn('password: "admin"', js_conf)

    def test_write_gui_config_no_analytics(self):
        write_gui_config(
            False, 'This is login help.', False, False, self.charmworld_url,
            self.build_dir, use_analytics=False, config_js_path='config')
        self.assertIn('useAnalytics: false', self.files['config'])

    def test_write_gui_config_fullscreen(self):
        write_gui_config(
            False, 'This is login help.', False, False, self.charmworld_url,
            self.build_dir, sandbox=True, default_viewmode='fullscreen',
            config_js_path='config')
        self.assertIn('defaultViewmode: "fullscreen"', self.files['config'])

    def test_write_gui_config_with_button(self):
        write_gui_config(
            False, 'This is login help.', False, False, self.charmworld_url,
            self.build_dir, sandbox=True, show_get_juju_button=True,
            config_js_path='config')
        self.assertIn('showGetJujuButton: true', self.files['config'])


class TestNpmCache(unittest.TestCase):
    """To speed building from a branch we prepopulate the NPM cache."""

    def test_retrieving_cache_url(self):
        # The URL for the latest cache file can be retrieved from Launchpad.
        class FauxLaunchpadFactory(object):
            @staticmethod
            def login_anonymously(agent, site):
                # We download the cache from the production site.
                self.assertEqual(site, 'production')
                return FauxLaunchpad

        class CacheFile(object):
            file_link = 'http://launchpad.example/path/to/cache/file'

            def __str__(self):
                return 'cache-file-123.tgz'

        class NpmRelease(object):
            files = [CacheFile()]

        class NpmSeries(object):
            name = 'npm-cache'
            releases = [NpmRelease]

        class FauxProject(object):
            series = [NpmSeries]

        class FauxLaunchpad(object):
            projects = {'juju-gui': FauxProject()}

        url = get_npm_cache_archive_url(Launchpad=FauxLaunchpadFactory())
        self.assertEqual(url, 'http://launchpad.example/path/to/cache/file')


if __name__ == '__main__':
    unittest.main(verbosity=2)
