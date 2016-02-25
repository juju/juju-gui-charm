# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2012-2014 Canonical Ltd.
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
import os
import shutil
from subprocess import CalledProcessError
import tempfile
import unittest
import yaml

import mock
from shelltoolbox import environ
import tempita

from utils import (
    JUJU_GUI_DIR,
    JUJU_PEM,
    RESTART,
    STOP,
    _get_by_attr,
    cmd_log,
    get_api_address,
    get_launchpad_release,
    get_port,
    get_release_file_path,
    install_builtin_server,
    install_missing_packages,
    log_hook,
    port_in_range,
    render_to_file,
    save_or_create_certificates,
    setup_ports,
    start_builtin_server,
    stop_builtin_server,
    write_builtin_server_startup,
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


class TestGetReleaseFilePath(unittest.TestCase):

    def setUp(self):
        self.playground = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.playground)

    def mock_releases_dir(self):
        """Mock the releases directory."""
        return mock.patch('utils.RELEASES_DIR', self.playground)

    def assert_path(self, filename, path):
        """Ensure the absolute path of filename equals the given path."""
        expected = os.path.join(self.playground, filename)
        self.assertEqual(expected, path)

    @contextmanager
    def assert_error(self):
        """Ensure the code executed in the context block raises a ValueError.

        Also check the error message.
        """
        with self.assertRaises(ValueError) as context_manager:
            yield
        error = str(context_manager.exception)
        self.assertEqual('Error: no releases found in the charm.', error)

    def add(self, filename):
        """Create a release file in the playground directory."""
        path = os.path.join(self.playground, filename)
        open(path, 'w').close()

    def test_last_release(self):
        # The last release is correctly retrieved.
        self.add('juju-gui-0.12.1.tgz')
        self.add('juju-gui-1.2.3.tgz')
        self.add('juju-gui-2.0.0+build.42.tgz')
        self.add('juju-gui-2.0.1.tgz')
        with self.mock_releases_dir():
            path = get_release_file_path()
        self.assert_path('juju-gui-2.0.1.tgz', path)

    def test_xz(self):
        # The last release is correctly retrieved for xz files too.
        self.add('juju-gui-0.12.1.tgz')
        self.add('juju-gui-1.2.3.tgz')
        self.add('juju-gui-2.0.0+build.42.tgz')
        self.add('juju-gui-2.0.1.xz')
        with self.mock_releases_dir():
            path = get_release_file_path()
        self.assert_path('juju-gui-2.0.1.xz', path)

    def test_tar_bz2(self):
        # The last release is correctly retrieved for tar.bz2 files too.
        self.add('juju-gui-0.12.1.tgz')
        self.add('juju-gui-1.2.3.tgz')
        self.add('juju-gui-2.0.0+build.42.tgz')
        self.add('jujugui-2.0.1.tar.bz2')
        with self.mock_releases_dir():
            path = get_release_file_path()
        self.assert_path('jujugui-2.0.1.tar.bz2', path)

    def test_xz_git_dev(self):
        # The last release is correctly retrieved.
        self.add('juju-gui-0.12.1.tgz')
        self.add('juju-gui-1.2.3.tgz')
        self.add('juju-gui-2.0.0+build.42.tgz')
        self.add('juju-gui-2.0.1.tgz')
        self.add('juju-gui-2.1.0+build.42a.xz')
        with self.mock_releases_dir():
            path = get_release_file_path()
        self.assert_path('juju-gui-2.1.0+build.42a.xz', path)

    def test_ordering(self):
        # Release versions are correctly ordered.
        self.add('juju-gui-0.12.1.tgz')
        self.add('juju-gui-0.9.1.tgz')
        with self.mock_releases_dir():
            path = get_release_file_path()
        self.assert_path('juju-gui-0.12.1.tgz', path)

    def test_no_releases(self):
        # A ValueError is raised if no releases are found.
        with self.mock_releases_dir():
            with self.assert_error():
                get_release_file_path()

    def test_no_releases_with_files(self):
        # A ValueError is raised if no releases are found.
        # Extraneous files are ignored while looking for releases.
        self.add('hujugui-1.2.3.tgz')  # Wrong prefix.
        self.add('juju-gui-1.2.tgz')  # Missing patch version number.
        self.add('juju-gui-1.2.3.bz2')  # Wrong file extension.
        self.add('juju-gui-1.2.3.4.tgz')  # Wrong version.
        self.add('juju-gui-1.2.3.build.42.tgz')  # Missing "+" separator.
        self.add('juju-gui-1.2.3+built.42.tgz')  # Typo.
        self.add('juju-gui-1.2.3+build.42.47.tgz')  # Invalid revno.
        self.add('juju-gui-1.2.3+build.42.bz2')  # Wrong file extension again.
        with self.mock_releases_dir():
            with self.assert_error():
                print get_release_file_path()

    def test_stable_version(self):
        # A specific stable version is correctly retrieved.
        self.add('juju-gui-1.2.3.tgz')
        self.add('juju-gui-2.0.1+build.42.tgz')
        self.add('juju-gui-2.0.1.tgz')
        self.add('juju-gui-3.2.1.tgz')
        with self.mock_releases_dir():
            path = get_release_file_path('2.0.1')
        self.assert_path('juju-gui-2.0.1.tgz', path)

    def test_development_version(self):
        # A specific development version is correctly retrieved.
        self.add('juju-gui-1.2.3+build.4247.tgz')
        self.add('juju-gui-2.42.47+build.4247.tgz')
        self.add('juju-gui-2.42.47.tgz')
        self.add('juju-gui-3.42.47+build.4247.tgz')
        with self.mock_releases_dir():
            path = get_release_file_path('2.42.47+build.4247')
        self.assert_path('juju-gui-2.42.47+build.4247.tgz', path)

    def test_xz_git_development_version(self):
        # A specific development version is correctly retrieved.
        self.add('juju-gui-1.2.3+build.4247.tgz')
        self.add('juju-gui-2.42.47+build.42b7.xz')
        self.add('juju-gui-2.42.47.tgz')
        self.add('juju-gui-3.42.47+build.4247.tgz')
        with self.mock_releases_dir():
            path = get_release_file_path('2.42.47+build.42b7')
        self.assert_path('juju-gui-2.42.47+build.42b7.xz', path)

    def test_version_not_found(self):
        # None is returned if the requested version is not found.
        self.add('juju-gui-1.2.3.tgz')
        self.add('juju-GUI-1.42.47.tgz')  # This is not a valid release.
        with self.mock_releases_dir():
            path = get_release_file_path('1.42.47')
        self.assertIsNone(path)


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


class TestGetLaunchpadRelease(unittest.TestCase):

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
        url, name = get_launchpad_release(self.project, 'stable', None)
        self.assertEqual('http://example.com/0.1.1.tgz', url)
        self.assertEqual('0.1.1.tgz', name)

    def test_specific_stable_release(self):
        # Ensure the correct URL is returned for a specific version of the
        # stable release.
        url, name = get_launchpad_release(self.project, 'stable', '0.1.0')
        self.assertEqual('http://example.com/0.1.0.tgz', url)
        self.assertEqual('0.1.0.tgz', name)

    def test_series_not_found(self):
        # A ValueError is raised if the series cannot be found.
        with self.assertRaises(ValueError) as cm:
            get_launchpad_release(self.project, 'unstable', None)
        self.assertIn('series not found', str(cm.exception))

    def test_no_releases(self):
        # A ValueError is raised if the series does not contain releases.
        project = AttrDict(series=[AttrDict(name='stable', releases=[])])
        with self.assertRaises(ValueError) as cm:
            get_launchpad_release(project, 'stable', None)
        self.assertIn('series does not contain releases', str(cm.exception))

    def test_release_not_found(self):
        # A ValueError is raised if the release cannot be found.
        with self.assertRaises(ValueError) as cm:
            get_launchpad_release(self.project, 'stable', '2.0')
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
            get_launchpad_release(project, 'stable', None)
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
        url, name = get_launchpad_release(project, 'stable', None)
        self.assertEqual('http://example.com/0.1.0.tgz', url)
        self.assertEqual('0.1.0.tgz', name)

    def test_xz_files_are_found(self):
        project = AttrDict(
            series=[
                AttrDict(
                    name='stable',
                    releases=[
                        AttrDict(
                            version='0.1.0',
                            files=[FileStub('http://example.com/0.1.0.xz')],
                        ),
                    ],
                ),
            ],
        )
        url, name = get_launchpad_release(project, 'stable', None)
        self.assertEqual('http://example.com/0.1.0.xz', url)
        self.assertEqual('0.1.0.xz', name)


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

    def mock_get_config(self):
        return self.mock_config

    def setUp(self):
        fd, self.log_file_name = tempfile.mkstemp()
        os.close(fd)
        self.mock_config = {'command-log-file': self.log_file_name}

    def test_contents_logged(self):
        with mock.patch('utils.get_config', self.mock_get_config):
            cmd_log('foo')
        line = open(self.log_file_name, 'r').read()
        self.assertTrue(line.endswith(': juju-gui@INFO \nfoo\n'))


class TestStartGui(unittest.TestCase):
    # XXX frankban 2014-12-10: change this test case so that functions being
    # tested are better separated. Also avoid manually patching helper
    # functions and use the mock library instead.

    def setUp(self):
        self.service_names = []
        self.actions = []
        self.svc_ctl_call_count = 0
        self.run_call_count = 0
        self.fake_zk_address = '192.168.5.26'
        self.build_dir = 'juju-gui/build-'
        self.charmworld_url = 'http://charmworld.example.com/'
        self.charmstore_url = 'http://charmstore.example.com/'
        self.ssl_cert_path = 'ssl/cert/path'

        # Monkey patches.

        def service_mock(action, service_name):
            self.svc_ctl_call_count += 1
            self.service_names.append(service_name)
            self.actions.append(action)

        def noop(*args):
            pass

        def run(*args):
            self.run_call_count += 1
            return ''

        @contextmanager
        def su(user):
            yield None

        self.files = {}
        orig_rtf = utils.render_to_file

        def render_to_file(template, context, dest):
            target = tempfile.NamedTemporaryFile()
            orig_rtf(template, context, target.name)
            with open(target.name, 'r') as fp:
                self.files[os.path.basename(dest)] = fp.read()

        self.utils_names = dict(
            service=(utils.service, service_mock),
            log=(utils.log, noop),
            su=(utils.su, su),
            run=(utils.run, run),
            render_to_file=(utils.render_to_file, render_to_file),
            get_api_address=(utils.get_api_address, noop),
        )
        # Apply the patches.
        for fn, fcns in self.utils_names.items():
            setattr(utils, fn, fcns[1])

        self.shutil_copy = shutil.copy
        shutil.copy = noop
        self.os_chmod = os.chmod
        os.chmod = noop

    def tearDown(self):
        # Undo all of the monkey patching.
        for fn, fcns in self.utils_names.items():
            setattr(utils, fn, fcns[0])
        shutil.copy = self.shutil_copy
        os.chmod = self.os_chmod

    def test_install_builtin_server(self):
        install_builtin_server()
        # Two run calls are executed: one for the dependencies, one for the
        # server itself.
        self.assertEqual(2, self.run_call_count)

    def test_write_builtin_server_startup(self):
        write_builtin_server_startup(
            self.ssl_cert_path, serve_tests=True, insecure=True,
            charmworld_url=self.charmworld_url)
        guiserver_conf = self.files['runserver.sh']
        self.assertIn('description "GUIServer"', guiserver_conf)
        self.assertIn('--logging="info"', guiserver_conf)
        # The get_api_address is noop'd in these tests so the addr is None.
        self.assertIn('--apiurl="wss://None"', guiserver_conf)
        self.assertIn('--apiversion="go"', guiserver_conf)
        self.assertIn(
            '--testsroot="{}/test/"'.format(JUJU_GUI_DIR), guiserver_conf)
        self.assertIn('--insecure', guiserver_conf)
        self.assertNotIn('--sandbox', guiserver_conf)
        self.assertIn('--charmworldurl="http://charmworld.example.com/"',
                      guiserver_conf)
        # By default the port is not provided to the GUI server.
        self.assertNotIn('--port', guiserver_conf)

    def test_write_builtin_server_startup_with_port(self):
        # The builtin server Upstart file is properly generated when a
        # customized port is provided.
        write_builtin_server_startup(self.ssl_cert_path, port=8000)
        guiserver_conf = self.files['runserver.sh']
        self.assertIn('--port=8000', guiserver_conf)

    def test_write_builtin_server_startup_sandbox_and_logging(self):
        # The upstart configuration file for the GUI server is correctly
        # generated when the GUI is in sandbox mode and when a customized log
        # level is specified.
        write_builtin_server_startup(
            self.ssl_cert_path, serve_tests=True, sandbox=True,
            builtin_server_logging='debug')
        guiserver_conf = self.files['runserver.sh']
        self.assertIn('description "GUIServer"', guiserver_conf)
        self.assertIn('--logging="debug"', guiserver_conf)
        self.assertIn('--sandbox', guiserver_conf)
        self.assertNotIn('--apiurl', guiserver_conf)
        self.assertNotIn('--apiversion', guiserver_conf)

    def test_write_builtin_server_startup_with_jem(self):
        # The builtin server Upstart file is properly generated with JEM.
        write_builtin_server_startup(
            self.ssl_cert_path, jem_location='https://1.2.3.4/jem',
            interactive_login=True)
        guiserver_conf = self.files['runserver.sh']
        self.assertIn('--jemlocation="https://1.2.3.4/jem"', guiserver_conf)
        self.assertIn('--interactivelogin="True"', guiserver_conf)

    def test_start_builtin_server(self):
        start_builtin_server(
            self.ssl_cert_path, serve_tests=False, sandbox=False,
            builtin_server_logging='info', insecure=False,
            charmworld_url='http://charmworld.example.com/', port=443)
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['guiserver'])
        self.assertEqual(self.actions, [RESTART])

    def test_stop_builtin_server(self):
        stop_builtin_server()
        self.assertEqual(self.svc_ctl_call_count, 1)
        self.assertEqual(self.service_names, ['guiserver'])
        self.assertEqual(self.actions, [STOP])
        self.assertEqual(self.run_call_count, 1)


class TestPortInRange(unittest.TestCase):

    def test_valid_port(self):
        # True is returned if the port is in range.
        for port in (1, 80, 443, 1234, 8080, 54321, 65535):
            self.assertTrue(port_in_range(port), port)

    def test_invalid_port(self):
        # False is returned if the port is not in range.
        for port in (-10, 0, 65536, 100000):
            self.assertFalse(port_in_range(port), port)


@mock.patch('utils.close_port')
@mock.patch('utils.open_port')
@mock.patch('utils.log')
class TestSetupPorts(unittest.TestCase):

    def test_default_ports(self, mock_log, mock_open_port, mock_close_port):
        # The default ports are properly opened.
        setup_ports(None, None)
        mock_log.assert_called_once_with('Opening default ports 80 and 443.')
        self.assertEqual(2, mock_open_port.call_count)
        mock_open_port.assert_has_calls([mock.call(80), mock.call(443)])
        self.assertFalse(mock_close_port.called)

    def test_from_defaults_to_new_port(
            self, mock_log, mock_open_port, mock_close_port):
        # The user provides a customized port.
        setup_ports(None, 8080)
        self.assertEqual(2, mock_log.call_count)
        mock_log.assert_has_calls([
            mock.call('Closing default ports 80 and 443.'),
            mock.call('Opening user provided port 8080.'),
        ])
        mock_open_port.assert_called_once_with(8080)
        self.assertEqual(2, mock_close_port.call_count)
        mock_close_port.assert_has_calls([mock.call(80), mock.call(443)])

    def test_from_previous_port_to_new_port(
            self, mock_log, mock_open_port, mock_close_port):
        # The user switches from a previously provided port to a new one.
        setup_ports(8080, 1234)
        self.assertEqual(3, mock_log.call_count)
        mock_log.assert_has_calls([
            mock.call('Closing user provided port 8080.'),
            # Always close the default ports in those cases.
            mock.call('Closing default ports 80 and 443.'),
            mock.call('Opening user provided port 1234.')
        ])
        mock_open_port.assert_called_once_with(1234)
        self.assertEqual(3, mock_close_port.call_count)
        mock_close_port.assert_has_calls([
            mock.call(8080), mock.call(80), mock.call(443)])

    def test_from_previous_port_to_defaults(
            self, mock_log, mock_open_port, mock_close_port):
        # The user provided a port and then switches back to defaults.
        setup_ports(1234, None)
        self.assertEqual(2, mock_log.call_count)
        mock_log.assert_has_calls([
            mock.call('Closing user provided port 1234.'),
            mock.call('Opening default ports 80 and 443.'),
        ])
        self.assertEqual(2, mock_open_port.call_count)
        mock_open_port.assert_has_calls([mock.call(80), mock.call(443)])
        mock_close_port.assert_called_once_with(1234)

    def test_from_previous_port_to_invalid(
            self, mock_log, mock_open_port, mock_close_port):
        # The user switches from a previously provided port to an invalid one.
        setup_ports(8080, 0)
        self.assertEqual(3, mock_log.call_count)
        mock_log.assert_has_calls([
            mock.call('Closing user provided port 8080.'),
            mock.call('Ignoring provided port 0: not in range.'),
            mock.call('Opening default ports 80 and 443.'),
        ])
        self.assertEqual(2, mock_open_port.call_count)
        mock_open_port.assert_has_calls([mock.call(80), mock.call(443)])
        mock_close_port.assert_called_once_with(8080)

    def test_from_defaults_to_invalid(
            self, mock_log, mock_open_port, mock_close_port):
        # The user provides an invalid port.
        setup_ports(None, 100000)
        self.assertEqual(2, mock_log.call_count)
        mock_log.assert_has_calls([
            mock.call('Ignoring provided port 100000: not in range.'),
            mock.call('Opening default ports 80 and 443.'),
        ])
        self.assertEqual(2, mock_open_port.call_count)
        mock_open_port.assert_has_calls([mock.call(80), mock.call(443)])
        self.assertFalse(mock_close_port.called)

    def test_from_invalid_to_new_port(
            self, mock_log, mock_open_port, mock_close_port):
        # The user fixes a previously provided invalid port.
        setup_ports(123456, 8000)
        self.assertEqual(2, mock_log.call_count)
        mock_log.assert_has_calls([
            mock.call('Closing default ports 80 and 443.'),
            mock.call('Opening user provided port 8000.')
        ])
        mock_open_port.assert_called_once_with(8000)
        self.assertEqual(2, mock_close_port.call_count)
        mock_close_port.assert_has_calls([mock.call(80), mock.call(443)])

    def test_from_invalid_to_defaults(
            self, mock_log, mock_open_port, mock_close_port):
        # The user switches back to default after providing an invalid port.
        setup_ports(0, None)
        mock_log.assert_called_once_with('Opening default ports 80 and 443.')
        self.assertEqual(2, mock_open_port.call_count)
        mock_open_port.assert_has_calls([mock.call(80), mock.call(443)])
        self.assertFalse(mock_close_port.called)


class TestGetPort(unittest.TestCase):

    def patch_config(self, data):
        """Simulate that the given data is the current charm configuration."""
        return mock.patch('utils.get_config', return_value=data)

    def test_secure_missing_port(self):
        with self.patch_config({'secure': True}):
            self.assertEqual(443, get_port())

    def test_secure_none_port(self):
        with self.patch_config({'port': None, 'secure': True}):
            self.assertEqual(443, get_port())

    def test_secure_customized_port(self):
        with self.patch_config({'port': 4242, 'secure': True}):
            self.assertEqual(4242, get_port())

    def test_missing_port(self):
        with self.patch_config({'secure': False}):
            self.assertEqual(80, get_port())

    def test_none_port(self):
        with self.patch_config({'port': None, 'secure': False}):
            self.assertEqual(80, get_port())

    def test_customized_port(self):
        with self.patch_config({'port': 4747, 'secure': False}):
            self.assertEqual(4747, get_port())


@mock.patch('utils.run')
@mock.patch('utils.log')
@mock.patch('utils.cmd_log', mock.Mock())
@mock.patch('utils.su', mock.MagicMock())
class TestInstallBuiltinServer(unittest.TestCase):

    def test_call(self, mock_log, mock_run):
        # The builtin server its correctly installed.
        install_builtin_server()
        charm_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..'))
        mock_log.assert_has_calls([
            mock.call('Installing the builtin server dependencies.'),
            mock.call('Installing the builtin server.'),
        ])
        mock_run.assert_has_calls([
            mock.call(
                'pip', 'install', '--no-index', '--no-dependencies',
                '--find-links', 'file:///{}/deps'.format(charm_dir),
                '-r', os.path.join(charm_dir, 'server-requirements.pip')),
            mock.call(
                '/usr/bin/python',
                os.path.join(charm_dir, 'server', 'setup.py'), 'install')
        ])


@mock.patch('utils.find_missing_packages')
@mock.patch('utils.install_extra_repositories')
@mock.patch('utils.apt_get_install')
@mock.patch('utils.log')
@mock.patch('utils.cmd_log', mock.Mock())
class TestInstallMissingPackages(unittest.TestCase):

    packages = ('pkg1', 'pkg2', 'pkg3')
    repository = 'ppa:my/repository'

    def test_missing(
            self, mock_log, mock_apt_get_install,
            mock_install_extra_repositories, mock_find_missing_packages):
        # The extra repository and packages are correctly installed.
        repository = self.repository
        mock_find_missing_packages.return_value = ['pkg1', 'pkg2']
        install_missing_packages(self.packages, repository=repository)
        mock_find_missing_packages.assert_called_once_with(*self.packages)
        mock_install_extra_repositories.assert_called_once_with(repository)
        mock_apt_get_install.assert_called_once_with('pkg1', 'pkg2')
        mock_log.assert_has_calls([
            mock.call('Adding the apt repository ppa:my/repository.'),
            mock.call('Installing deb packages: pkg1, pkg2.')
        ])

    def test_missing_no_repository(
            self, mock_log, mock_apt_get_install,
            mock_install_extra_repositories, mock_find_missing_packages):
        # No repositories are installed if not passed.
        mock_find_missing_packages.return_value = ['pkg1', 'pkg2']
        install_missing_packages(self.packages)
        mock_find_missing_packages.assert_called_once_with(*self.packages)
        self.assertFalse(mock_install_extra_repositories.called)
        mock_apt_get_install.assert_called_once_with('pkg1', 'pkg2')
        mock_log.assert_called_once_with(
            'Installing deb packages: pkg1, pkg2.')

    def test_no_missing(
            self, mock_log, mock_apt_get_install,
            mock_install_extra_repositories, mock_find_missing_packages):
        # Nothing is installed if no missing packages are found.
        mock_find_missing_packages.return_value = []
        install_missing_packages(self.packages, repository=self.repository)
        mock_find_missing_packages.assert_called_once_with(*self.packages)
        self.assertFalse(mock_install_extra_repositories.called)
        self.assertFalse(mock_apt_get_install.called)
        mock_log.assert_called_once_with('No missing deb packages.')


if __name__ == '__main__':
    unittest.main(verbosity=2)
