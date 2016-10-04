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
from shelltoolbox import run
import shutil
import tempfile
import unittest

import mock

import backend
import utils


EXPECTED_DEBS = (
    'curl', 'libcurl3', 'openssl', 'python-bzrlib', 'python-pip',
    'python-pycurl')

JUJU_VERSION = run('jujud', '--version').strip()


def patch_environ(**kwargs):
    """Patch the environment context by adding the given kwargs."""
    environ = os.environ.copy()
    environ.update(kwargs)
    return mock.patch('os.environ', environ)


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
            'ssl-cert-path': self.ssl_cert_path,
            'bundleservice-url': '',
            'interactive-login': False,
            'gzip-compression': True,
            'gtm-enabled': False,
            'gisf-enabled': False,
        }
        if options is not None:
            config.update(options)
        return config

    @contextmanager
    def mock_all(self):
        """Mock all the extrenal functions used by the backend framework."""
        mocks = {
            'base_dir': mock.patch('backend.utils.BASE_DIR', self.base_dir),
            'install_builtin_server': mock.patch(
                'backend.utils.install_builtin_server'),
            'install_missing_packages': mock.patch(
                'backend.utils.install_missing_packages'),
            'log': mock.patch('backend.log'),
            'save_or_create_certificates': mock.patch(
                'backend.utils.save_or_create_certificates'),
            'setup_gui': mock.patch('backend.utils.setup_gui'),
            'setup_ports': mock.patch('backend.utils.setup_ports'),
            'start_builtin_server': mock.patch(
                'backend.utils.start_builtin_server'),
            'stop_builtin_server': mock.patch(
                'backend.utils.stop_builtin_server'),
        }
        # Note: nested is deprecated for good reasons which do not apply here.
        # Used here to easily nest a dynamically generated list of context
        # managers.
        with nested(*mocks.values()) as context_managers:
            object_dict = dict(zip(mocks.keys(), context_managers))
            yield type('Mocks', (object,), object_dict)

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

    def test_install(self):
        # Install a stable release.
        test_backend = backend.Backend(config=self.make_config())
        with self.mock_all() as mocks:
            test_backend.install()
        mocks.install_missing_packages.assert_called_once_with(
            set(EXPECTED_DEBS))
        mocks.setup_gui.assert_called_once_with()
        mocks.install_builtin_server.assert_called_once_with()

    def test_start(self):
        # Start the GUI server.
        config = self.make_config()
        test_backend = backend.Backend(config=config)
        with self.mock_all() as mocks:
            with patch_environ(JUJU_MODEL_UUID='model-uuid'):
                test_backend.start()
        mocks.start_builtin_server.assert_called_once_with(
            self.ssl_cert_path,
            config['serve-tests'],
            config['sandbox'],
            config['builtin-server-logging'],
            False,                        # insecure
            config['charmworld-url'],
            charmstore_url='http://charmstore.example.com/',
            bundleservice_url='',
            env_uuid='model-uuid',
            interactive_login=False,
            juju_version=JUJU_VERSION,
            debug=False,
            gtm_enabled=False,
            gisf_enabled=False,
            gzip=True,
            port=None,
            env_password=None)

    def test_start_uuid_pre2(self):
        # Start the GUI server with Juju < 2.0.
        config = self.make_config()
        test_backend = backend.Backend(config=config)
        with self.mock_all() as mocks:
            with patch_environ(JUJU_ENV_UUID='env-uuid'):
                test_backend.start()
        mocks.start_builtin_server.assert_called_once_with(
            self.ssl_cert_path,
            config['serve-tests'],
            config['sandbox'],
            config['builtin-server-logging'],
            False,                        # insecure
            config['charmworld-url'],
            charmstore_url='http://charmstore.example.com/',
            bundleservice_url='',
            env_uuid='env-uuid',
            interactive_login=False,
            juju_version=JUJU_VERSION,
            debug=False,
            gtm_enabled=False,
            gisf_enabled=False,
            gzip=True,
            port=None,
            env_password=None)

    def test_start_uuid_error(self):
        # A ValueError is raised if the model UUID cannot be found in the hook
        # context.
        config = self.make_config()
        test_backend = backend.Backend(config=config)
        with self.mock_all():
            with self.assertRaises(ValueError) as ctx:
                test_backend.start()
        self.assertEqual(
            'cannot retrieve model UUID from hook context',
            ctx.exception.message)

    def test_start_insecure_ws_secure(self):
        # It is possible to configure the service so that, even if the GUI
        # server runs in insecure mode, the client still connects via a secure
        # WebSocket connection. This is often used when proxying the GUI behind
        # an SSL terminating service like Apache2.
        config = self.make_config({'secure': False, 'ws-secure': True})
        test_backend = backend.Backend(config=config)
        with self.mock_all() as mocks:
            with patch_environ(JUJU_MODEL_UUID='uuid'):
                test_backend.start()
        mocks.start_builtin_server.assert_called_once_with(
            self.ssl_cert_path,
            config['serve-tests'],
            config['sandbox'],
            config['builtin-server-logging'],
            True,                         # insecure
            config['charmworld-url'],
            charmstore_url='http://charmstore.example.com/',
            bundleservice_url='',
            env_uuid='uuid',
            interactive_login=False,
            juju_version=JUJU_VERSION,
            debug=False,
            gtm_enabled=False,
            gisf_enabled=False,
            gzip=True,
            port=None,
            env_password=None)

    def test_gisf_enabled(self):
        config = self.make_config({'gisf-enabled': True})
        test_backend = backend.Backend(config=config)
        with self.mock_all() as mocks:
            with patch_environ(JUJU_MODEL_UUID='uuid'):
                test_backend.start()
        mocks.start_builtin_server.assert_called_once_with(
            self.ssl_cert_path,
            config['serve-tests'],
            config['sandbox'],
            config['builtin-server-logging'],
            False,                        # insecure
            config['charmworld-url'],
            charmstore_url='http://charmstore.example.com/',
            bundleservice_url='',
            env_uuid='uuid',
            interactive_login=False,
            juju_version=JUJU_VERSION,
            debug=False,
            gtm_enabled=False,
            gisf_enabled=True,
            gzip=True,
            port=None,
            env_password=None)

    def test_sandbox_mode_forces_juju_2(self):
        # Start the GUI server.
        config = self.make_config(options=dict(sandbox=True))
        test_backend = backend.Backend(config=config)
        with self.mock_all() as mocks:
            with patch_environ(JUJU_MODEL_UUID='model-uuid'):
                test_backend.start()
        mocks.start_builtin_server.assert_called_once_with(
            self.ssl_cert_path,
            config['serve-tests'],
            config['sandbox'],
            config['builtin-server-logging'],
            False,                        # insecure
            config['charmworld-url'],
            charmstore_url='http://charmstore.example.com/',
            bundleservice_url='',
            env_uuid='model-uuid',
            interactive_login=False,
            juju_version='2.0.0',
            debug=False,
            gtm_enabled=False,
            gisf_enabled=False,
            gzip=True,
            port=None,
            env_password=None)

    @unittest.skip("start config not done")
    def test_start_user_provided_port(self):
        # Start the GUI server with a user provided port.
        config = self.make_config({'port': 8080})
        test_backend = backend.Backend(config=config)
        with self.mock_all() as mocks:
            test_backend.start()
        mocks.setup_ports.assert_called_once_with(None, 8080)
        mocks.start_builtin_server.assert_called_once_with(
            self.ssl_cert_path,
            config['serve-tests'], config['sandbox'],
            config['builtin-server-logging'],
            not config['secure'],
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
