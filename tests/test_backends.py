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


from collections import defaultdict
from contextlib import contextmanager
import shutil
import tempfile
import unittest

import charmhelpers
import mock
import shelltoolbox

import backend
import utils


def get_mixin_names(test_backend):
    return tuple(b.__class__.__name__ for b in test_backend.mixins)


class GotEmAllDict(defaultdict):
    """A dictionary that returns the same default value for all given keys."""

    def get(self, key, default=None):
        return self.default_factory()


class TestBackendProperties(unittest.TestCase):
    """Ensure the correct mixins and property values are collected."""

    simulate_pyjuju = mock.patch(
        'utils.legacy_juju', mock.Mock(return_value=True))
    simulate_juju_core = mock.patch(
        'utils.legacy_juju', mock.Mock(return_value=False))

    def check_sandbox_mode(self):
        """The backend includes the correct mixins when sandbox mode is active.
        """
        test_backend = backend.Backend(config={
            'sandbox': True, 'staging': False, 'builtin-server': False})
        mixin_names = get_mixin_names(test_backend)
        self.assertEqual(
            ('SandboxMixin', 'GuiMixin', 'HaproxyApacheMixin'),
            mixin_names)
        self.assertEqual(
            frozenset(('apache2', 'curl', 'haproxy', 'openssl')),
            test_backend.debs)

    def test_python_staging_backend(self):
        with self.simulate_pyjuju:
            test_backend = backend.Backend(config={
                'sandbox': False, 'staging': True, 'builtin-server': False})
            mixin_names = get_mixin_names(test_backend)
            self.assertEqual(
                ('ImprovMixin', 'GuiMixin', 'HaproxyApacheMixin'),
                mixin_names)
            debs = ('apache2', 'curl', 'haproxy', 'openssl', 'zookeeper')
            self.assertEqual(frozenset(debs), test_backend.debs)

    def test_go_staging_backend(self):
        config = {'sandbox': False, 'staging': True, 'builtin-server': False}
        with self.simulate_juju_core:
            with self.assertRaises(ValueError) as context_manager:
                backend.Backend(config=config)
        error = str(context_manager.exception)
        self.assertEqual('Unable to use staging with go backend', error)

    def test_python_sandbox_backend(self):
        with self.simulate_pyjuju:
            self.check_sandbox_mode()

    def test_go_sandbox_backend(self):
        with self.simulate_juju_core:
            self.check_sandbox_mode()

    def test_python_backend(self):
        with self.simulate_pyjuju:
            test_backend = backend.Backend(config={
                'sandbox': False, 'staging': False, 'builtin-server': False})
            mixin_names = get_mixin_names(test_backend)
            self.assertEqual(
                ('PythonMixin', 'GuiMixin', 'HaproxyApacheMixin'),
                mixin_names)
            self.assertEqual(
                frozenset(('apache2', 'curl', 'haproxy', 'openssl')),
                test_backend.debs)

    def test_go_backend(self):
        with self.simulate_juju_core:
            test_backend = backend.Backend(config={
                'sandbox': False, 'staging': False, 'builtin-server': False})
            mixin_names = get_mixin_names(test_backend)
            self.assertEqual(
                ('GoMixin', 'GuiMixin', 'HaproxyApacheMixin'),
                mixin_names)
            self.assertEqual(
                frozenset(
                    ('apache2', 'curl', 'haproxy', 'openssl', 'python-yaml')),
                test_backend.debs)

    def test_builtin_server(self):
        expected_mixins = ('GoMixin', 'GuiMixin', 'BuiltinServerMixin')
        expected_debs = set([
            'python-pip', 'python-yaml', 'curl', 'openssl', 'python-bzrlib'])
        with self.simulate_juju_core:
            test_backend = backend.Backend(config={
                'sandbox': False, 'staging': False, 'builtin-server': True})
            mixin_names = get_mixin_names(test_backend)
            self.assertEqual(expected_mixins, mixin_names)
            self.assertEqual(expected_debs, test_backend.debs)


class TestBackendCommands(unittest.TestCase):

    def setUp(self):
        self.called = {}
        self.alwaysFalse = GotEmAllDict(lambda: False)
        self.alwaysTrue = GotEmAllDict(lambda: True)

        # Monkeypatch functions.
        self.utils_mocks = {
            'compute_build_dir': utils.compute_build_dir,
            'fetch_api': utils.fetch_api,
            'fetch_gui_from_branch': utils.fetch_gui_from_branch,
            'fetch_gui_release': utils.fetch_gui_release,
            'find_missing_packages': utils.find_missing_packages,
            'get_api_address': utils.get_api_address,
            'get_npm_cache_archive_url': utils.get_npm_cache_archive_url,
            'install_builtin_server': utils.install_builtin_server,
            'parse_source': utils.parse_source,
            'prime_npm_cache': utils.prime_npm_cache,
            'remove_apache_setup': utils.remove_apache_setup,
            'remove_haproxy_setup': utils.remove_haproxy_setup,
            'save_or_create_certificates': utils.save_or_create_certificates,
            'setup_apache_config': utils.setup_apache_config,
            'setup_gui': utils.setup_gui,
            'setup_haproxy_config': utils.setup_haproxy_config,
            'start_agent': utils.start_agent,
            'start_improv': utils.start_improv,
            'write_builtin_server_startup': utils.write_builtin_server_startup,
            'write_gui_config': utils.write_gui_config,
        }
        self.charmhelpers_mocks = {
            'log': charmhelpers.log,
            'open_port': charmhelpers.open_port,
            'service_control': charmhelpers.service_control,
        }

        def make_mock_function(name):
            def mock_function(*args, **kwargs):
                self.called[name] = True
                return (None, None)
            mock_function.__name__ = name
            return mock_function

        for name in self.utils_mocks.keys():
            setattr(utils, name, make_mock_function(name))
        for name in self.charmhelpers_mocks.keys():
            setattr(charmhelpers, name, make_mock_function(name))

        @contextmanager
        def mock_su(user):
            self.called['su'] = True
            yield
        self.orig_su = utils.su
        utils.su = mock_su

        def mock_apt_get_install(*debs):
            self.called['apt_get_install'] = True
        self.orig_apt_get_install = shelltoolbox.apt_get_install
        shelltoolbox.apt_get_install = mock_apt_get_install

        def mock_run(*debs):
            self.called['run'] = True
        self.orig_run = shelltoolbox.run
        shelltoolbox.run = mock_run

        # Monkeypatch directories.
        self.orig_juju_dir = utils.JUJU_DIR
        self.temp_dir = tempfile.mkdtemp()
        utils.JUJU_DIR = self.temp_dir

    def tearDown(self):
        # Cleanup directories.
        utils.JUJU_DIR = self.orig_juju_dir
        shutil.rmtree(self.temp_dir)
        # Undo the monkeypatching.
        shelltoolbox.run = self.orig_run
        shelltoolbox.apt_get_install = self.orig_apt_get_install
        utils.su = self.orig_su
        for name, orig_fun in self.charmhelpers_mocks.items():
            setattr(charmhelpers, name, orig_fun)
        for name, orig_fun in self.utils_mocks.items():
            setattr(utils, name, orig_fun)

    def test_install_python(self):
        test_backend = backend.Backend(config=self.alwaysFalse)
        test_backend.install()
        for mocked in (
            'apt_get_install', 'fetch_api', 'find_missing_packages',
        ):
            self.assertTrue(
                self.called.get(mocked), '{} was not called'.format(mocked))

    def test_install_improv_builtin(self):
        test_backend = backend.Backend(config=self.alwaysTrue)
        test_backend.install()
        for mocked in (
            'apt_get_install', 'fetch_api', 'find_missing_packages',
            'install_builtin_server',
        ):
            self.assertTrue(
                self.called.get(mocked), '{} was not called'.format(mocked))

    def test_start_agent(self):
        test_backend = backend.Backend(config=self.alwaysFalse)
        test_backend.start()
        for mocked in (
            'compute_build_dir', 'open_port', 'setup_apache_config',
            'setup_haproxy_config', 'start_agent', 'su', 'write_gui_config',
        ):
            self.assertTrue(
                self.called.get(mocked), '{} was not called'.format(mocked))

    def test_start_improv_builtin(self):
        test_backend = backend.Backend(config=self.alwaysTrue)
        test_backend.start()
        for mocked in (
            'compute_build_dir', 'open_port', 'start_improv', 'su',
            'write_builtin_server_startup', 'write_gui_config',
        ):
            self.assertTrue(
                self.called.get(mocked), '{} was not called'.format(mocked))

    def test_stop(self):
        test_backend = backend.Backend(config=self.alwaysFalse)
        test_backend.stop()
        self.assertTrue(self.called.get('su'), 'su was not called')


class TestBackendUtils(unittest.TestCase):

    def test_same_config(self):
        test_backend = backend.Backend(
            config={
                'sandbox': False, 'staging': False, 'builtin-server': False},
            prev_config={
                'sandbox': False, 'staging': False, 'builtin-server': False},
        )
        self.assertFalse(test_backend.different('sandbox'))
        self.assertFalse(test_backend.different('staging'))

    def test_different_config(self):
        test_backend = backend.Backend(
            config={
                'sandbox': False, 'staging': False, 'builtin-server': False},
            prev_config={
                'sandbox': True, 'staging': False, 'builtin-server': False},
        )
        self.assertTrue(test_backend.different('sandbox'))
        self.assertFalse(test_backend.different('staging'))
