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

"""Backend tests."""


from contextlib import (
    contextmanager,
    nested,
)
import os
import shutil
import tempfile
import unittest

import mock

import backend
import utils


EXPECTED_DEBS = (
    'curl', 'libcurl3', 'openssl', 'python-bzrlib', 'python-pip',
    'python-pycurl')


class TestBackendProperties(unittest.TestCase):
    """Ensure the correct mixins and property values are collected."""

    def test_mixins(self):
        # Ensure the backend includes the expected mixins.
        expected_mixins = ['SetUpMixin', 'GuiMixin', 'GuiServerMixin']
        test_backend = backend.Backend(config={})
        mixins = [mixin.__class__.__name__ for mixin in test_backend.mixins]
        self.assertEqual(expected_mixins, mixins)

    def test_dependencies(self):
        # Ensure the backend includes the expected dependencies.
        test_backend = backend.Backend(config={})
        self.assertEqual(set(EXPECTED_DEBS), test_backend.get_dependencies())


class TestBackendCommands(unittest.TestCase):

    def setUp(self):
        # Set up directories.
        self.playground = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.playground)
        self.base_dir = os.path.join(self.playground, 'juju-gui')
        self.command_log_file = os.path.join(self.playground, 'logs')
        self.ssl_cert_path = os.path.join(self.playground, 'ssl-cert-path')
        # Set up default values.
        self.juju_gui_source = 'stable'
        self.repository_location = 'ppa:my/location'
        self.parse_source_return_value = ('stable', None)

    def make_config(self, options=None):
        """Create and return a backend configuration dict."""
        config = {
            'builtin-server-logging': 'info',
            'cached-fonts': False,
            'charmworld-url': 'http://charmworld.example.com/',
            'charmstore-url': 'http://charmstore.example.com/',
            'command-log-file': self.command_log_file,
            'ga-key': 'my-key',
            'juju-gui-debug': False,
            'juju-gui-console-enabled': False,
            'juju-gui-source': self.juju_gui_source,
            'login-help': 'login-help',
            'read-only': False,
            'repository-location': self.repository_location,
            'sandbox': False,
            'secure': True,
            'serve-tests': False,
            'hide-login-button': False,
            'juju-core-version': '1.21',
            'ssl-cert-path': self.ssl_cert_path,
        }
        if options is not None:
            config.update(options)
        return config

    @contextmanager
    def mock_all(self):
        """Mock all the extrenal functions used by the backend framework."""
        mock_parse_source = mock.Mock(
            return_value=self.parse_source_return_value)
        mocks = {
            'base_dir': mock.patch('backend.utils.BASE_DIR', self.base_dir),
            'compute_build_dir': mock.patch('backend.utils.compute_build_dir'),
            'fetch_gui_from_branch': mock.patch(
                'backend.utils.fetch_gui_from_branch'),
            'fetch_gui_release': mock.patch('backend.utils.fetch_gui_release'),
            'install_builtin_server': mock.patch(
                'backend.utils.install_builtin_server'),
            'install_missing_packages': mock.patch(
                'backend.utils.install_missing_packages'),
            'log': mock.patch('backend.log'),
            'parse_source': mock.patch(
                'backend.utils.parse_source', mock_parse_source),
            'save_or_create_certificates': mock.patch(
                'backend.utils.save_or_create_certificates'),
            'setup_gui': mock.patch('backend.utils.setup_gui'),
            'setup_ports': mock.patch('backend.utils.setup_ports'),
            'start_builtin_server': mock.patch(
                'backend.utils.start_builtin_server'),
            'stop_builtin_server': mock.patch(
                'backend.utils.stop_builtin_server'),
            'write_gui_config': mock.patch('backend.utils.write_gui_config'),
        }
        # Note: nested is deprecated for good reasons which do not apply here.
        # Used here to easily nest a dynamically generated list of context
        # managers.
        with nested(*mocks.values()) as context_managers:
            object_dict = dict(zip(mocks.keys(), context_managers))
            yield type('Mocks', (object,), object_dict)

    def assert_write_gui_config_called(self, mocks, config):
        """Ensure the mocked write_gui_config has been properly called."""
        mocks.write_gui_config.assert_called_once_with(
            config['juju-gui-console-enabled'], config['login-help'],
            config['read-only'], config['charmworld-url'],
            config['charmstore-url'], mocks.compute_build_dir(),
            secure=config['secure'], sandbox=config['sandbox'],
            cached_fonts=config['cached-fonts'], ga_key=config['ga-key'],
            juju_core_version=config['juju-core-version'],
            hide_login_button=config['hide-login-button'],
            juju_env_uuid=None, password=None)

    def test_base_dir_created(self):
        # The base Juju GUI directory is correctly created.
        config = self.make_config()
        test_backend = backend.Backend(config=config)
        with self.mock_all():
            test_backend.install()
        self.assertTrue(os.path.isdir(self.base_dir))

    def test_base_dir_removed(self):
        # The base Juju GUI directory is correctly removed.
        config = self.make_config()
        test_backend = backend.Backend(config=config)
        with self.mock_all():
            test_backend.install()
            test_backend.destroy()
        self.assertFalse(os.path.exists(utils.BASE_DIR), utils.BASE_DIR)

    def test_install_stable_release(self):
        # Install a stable release.
        test_backend = backend.Backend(config=self.make_config())
        with self.mock_all() as mocks:
            test_backend.install()
        mocks.install_missing_packages.assert_called_once_with(
            set(EXPECTED_DEBS))
        mocks.parse_source.assert_called_once_with(self.juju_gui_source)
        mocks.fetch_gui_release.assert_called_once_with(
            *self.parse_source_return_value)
        self.assertFalse(mocks.fetch_gui_from_branch.called)
        mocks.setup_gui.assert_called_once_with(mocks.fetch_gui_release())
        mocks.install_builtin_server.assert_called_once_with()

    def test_install_branch_release(self):
        # Install a branch release.
        self.parse_source_return_value = ('branch', ('lp:juju-gui', 42))
        expected_calls = [
            mock.call(set(EXPECTED_DEBS)),
            mock.call(
                utils.DEB_BUILD_DEPENDENCIES,
                repository=self.repository_location,
            ),
        ]
        test_backend = backend.Backend(config=self.make_config())
        with self.mock_all() as mocks:
            test_backend.install()
        mocks.install_missing_packages.assert_has_calls(expected_calls)
        mocks.parse_source.assert_called_once_with(self.juju_gui_source)
        mocks.fetch_gui_from_branch.assert_called_once_with(
            'lp:juju-gui', 42, self.command_log_file)
        self.assertFalse(mocks.fetch_gui_release.called)
        mocks.setup_gui.assert_called_once_with(mocks.fetch_gui_from_branch())
        mocks.install_builtin_server.assert_called_once_with()

    def test_start(self):
        # Start the GUI server.
        config = self.make_config()
        test_backend = backend.Backend(config=config)
        with self.mock_all() as mocks:
            test_backend.start()
        mocks.compute_build_dir.assert_called_with(
            config['juju-gui-debug'], config['serve-tests'])
        self.assert_write_gui_config_called(mocks, config)
        mocks.setup_ports.assert_called_once_with(None, None)
        mocks.start_builtin_server.assert_called_once_with(
            mocks.compute_build_dir(), self.ssl_cert_path,
            config['serve-tests'], config['sandbox'],
            config['builtin-server-logging'], not config['secure'],
            config['charmworld-url'], port=None)

    def test_start_user_provided_port(self):
        # Start the GUI server with a user provided port.
        config = self.make_config({'port': 8080})
        test_backend = backend.Backend(config=config)
        with self.mock_all() as mocks:
            test_backend.start()
        mocks.setup_ports.assert_called_once_with(None, 8080)
        mocks.start_builtin_server.assert_called_once_with(
            mocks.compute_build_dir(), self.ssl_cert_path,
            config['serve-tests'], config['sandbox'],
            config['builtin-server-logging'], not config['secure'],
            config['charmworld-url'], port=8080)

    def test_stop(self):
        # Stop the GUI server.
        test_backend = backend.Backend(config=self.make_config())
        with self.mock_all() as mocks:
            test_backend.stop()
        mocks.stop_builtin_server.assert_called_once_with()


class TestBackendUtils(unittest.TestCase):

    def test_same_config(self):
        test_backend = backend.Backend(
            config={'sandbox': False, 'secure': False},
            prev_config={'sandbox': False, 'secure': False},
        )
        self.assertFalse(test_backend.different('sandbox'))
        self.assertFalse(test_backend.different('secure'))

    def test_different_config(self):
        test_backend = backend.Backend(
            config={'sandbox': False, 'secure': False},
            prev_config={'sandbox': True, 'secure': False},
        )
        self.assertTrue(test_backend.different('sandbox'))
        self.assertFalse(test_backend.different('secure'))


class TestCallMethods(unittest.TestCase):

    def setUp(self):
        self.called = []
        self.objects = [self.make_object('Obj1'), self.make_object('Obj2')]

    def make_object(self, name, has_method=True):
        """Create and return an test object with the given name."""
        def method(obj, *args):
            self.called.append([obj.__class__.__name__, args])
        object_dict = {'method': method} if has_method else {}
        return type(name, (object,), object_dict)()

    def test_call(self):
        # The methods are correctly called.
        backend.call_methods(self.objects, 'method', 'arg1', 'arg2')
        expected = [['Obj1', ('arg1', 'arg2')], ['Obj2', ('arg1', 'arg2')]]
        self.assertEqual(expected, self.called)

    def test_no_method(self):
        # An object without the method is ignored.
        self.objects.append(self.make_object('Obj3', has_method=False))
        backend.call_methods(self.objects, 'method')
        expected = [['Obj1', ()], ['Obj2', ()]]
        self.assertEqual(expected, self.called)
