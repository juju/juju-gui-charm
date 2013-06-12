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

from collections import defaultdict
from contextlib import contextmanager
import os
import shutil
import tempfile
import unittest

import charmhelpers
import shelltoolbox

import backend
import utils


def get_mixin_names(test_backend):
    return tuple(b.__class__.__name__ for b in test_backend.mixins)


class TestBackendProperties(unittest.TestCase):
    """
    As the number of configurations this charm supports increases it becomes
    desirable to move to Strategy pattern objects to implement features
    per backend. These tests insure the basic factory code works.
    """

    def test_staging_backend(self):
        test_backend = backend.Backend(
            config={'sandbox': False, 'staging': True})
        mixin_names = get_mixin_names(test_backend)
        self.assertEqual(
            ('InstallMixin', 'ImprovMixin', 'GuiMixin', 'UpstartMixin'),
            mixin_names)
        self.assertEqual(
            frozenset(('apache2', 'curl', 'haproxy', 'openssl', 'zookeeper')),
            test_backend.debs)
        self.assertEqual(
            frozenset(()),
            test_backend.repositories)
        self.assertEqual(
            frozenset(('haproxy.conf',)),
            test_backend.upstart_scripts)

    def test_sandbox_backend(self):
        test_backend = backend.Backend(
            config={'sandbox': True, 'staging': False})
        mixin_names = get_mixin_names(test_backend)
        self.assertEqual(
            ('InstallMixin', 'SandboxMixin', 'GuiMixin', 'UpstartMixin'),
            mixin_names)
        self.assertEqual(
            frozenset(('apache2', 'curl', 'haproxy', 'openssl')),
            test_backend.debs)
        self.assertEqual(
            frozenset(()),
            test_backend.repositories)
        self.assertEqual(
            frozenset(('haproxy.conf',)),
            test_backend.upstart_scripts)

    def test_python_backend(self):
        test_backend = backend.Backend(
            config={'sandbox': False, 'staging': False})
        mixin_names = get_mixin_names(test_backend)
        self.assertEqual(
            ('InstallMixin', 'PythonMixin', 'GuiMixin', 'UpstartMixin'),
            mixin_names)
        self.assertEqual(
            frozenset(('apache2', 'curl', 'haproxy', 'openssl')),
            test_backend.debs)
        self.assertEqual(
            frozenset(()),
            test_backend.repositories)
        self.assertEqual(
            frozenset(('haproxy.conf',)),
            test_backend.upstart_scripts)

    def test_go_backend(self):
        # Monkeypatch utils.CURRENT_DIR.
        base_dir = tempfile.mkdtemp()
        orig_current_dir = utils.CURRENT_DIR
        utils.CURRENT_DIR = tempfile.mkdtemp(dir=base_dir)
        # Create a fake agent file.
        agent_path = os.path.join(base_dir, 'agent.conf')
        open(agent_path, 'w').close()
        test_backend = backend.Backend(
            config={'sandbox': False, 'staging': False})
        # Cleanup.
        utils.CURRENT_DIR = orig_current_dir
        shutil.rmtree(base_dir)
        # Tests
        mixin_names = get_mixin_names(test_backend)
        self.assertEqual(
            ('InstallMixin', 'GoMixin', 'GuiMixin', 'UpstartMixin'),
            mixin_names)
        self.assertEqual(
            frozenset(
                ('apache2', 'curl', 'haproxy', 'openssl', 'python-yaml')),
            test_backend.debs)
        self.assertEqual(
            frozenset(()),
            test_backend.repositories)
        self.assertEqual(
            frozenset(('haproxy.conf',)),
            test_backend.upstart_scripts)


class GotEmAllDict(defaultdict):
    """A dictionary that returns the same default value for all given keys."""

    def get(self, key, default=None):
        return self.default_factory()


class TestBackendCommands(unittest.TestCase):

    def setUp(self):
        self.called = {}
        self.alwaysFalse = GotEmAllDict(lambda: False)
        self.alwaysTrue = GotEmAllDict(lambda: True)

        # Monkeypatch functions.
        self.utils_mocks = {
            'setup_apache': utils.setup_apache,
            'fetch_api': utils.fetch_api,
            'fetch_gui': utils.fetch_gui,
            'setup_gui': utils.setup_gui,
            'save_or_create_certificates': utils.save_or_create_certificates,
            'find_missing_packages': utils.find_missing_packages,
            'prime_npm_cache': utils.prime_npm_cache,
            'get_npm_cache_archive_url': utils.get_npm_cache_archive_url,
            'start_gui': utils.start_gui,
            'start_agent': utils.start_agent,
            'start_improv': utils.start_improv,
        }
        self.charmhelpers_mocks = {
            'log': charmhelpers.log,
            'open_port': charmhelpers.open_port,
            'service_control': charmhelpers.service_control,
        }

        def make_mock_function(name):
            def mock_function(*args, **kwargs):
                self.called[name] = True
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
        self.orig_su = shelltoolbox.su
        shelltoolbox.su = mock_su

        # Monkeypatch directories.
        self.orig_juju_dir = utils.JUJU_DIR
        self.orig_sys_init_dir = backend.SYS_INIT_DIR
        self.temp_dir = tempfile.mkdtemp()
        utils.JUJU_DIR = self.temp_dir
        backend.SYS_INIT_DIR = self.temp_dir

    def tearDown(self):
        # Cleanup directories.
        backend.SYS_INIT_DIR = self.orig_sys_init_dir
        utils.JUJU_DIR = self.orig_juju_dir
        shutil.rmtree(self.temp_dir)
        # Undo the monkeypatching.
        shelltoolbox.su = self.orig_su
        for name, orig_fun in self.charmhelpers_mocks.items():
            setattr(charmhelpers, name, orig_fun)
        for name, orig_fun in self.utils_mocks.items():
            setattr(utils, name, orig_fun)

    def test_install_python(self):
        test_backend = backend.Backend(config=self.alwaysFalse)
        test_backend.install()
        for mocked in (
                'find_missing_packages', 'setup_apache', 'fetch_api', 'log'):
            self.assertTrue(mocked, '{} was not called'.format(mocked))

    def test_install_improv(self):
        test_backend = backend.Backend(config=self.alwaysTrue)
        test_backend.install()
        for mocked in (
                'find_missing_packages', 'setup_apache', 'fetch_api', 'log'):
            self.assertTrue(mocked, '{} was not called'.format(mocked))

    def test_start_agent(self):
        test_backend = backend.Backend(config=self.alwaysFalse)
        test_backend.start()
        for mocked in (
                'service_control', 'start_agent', 'start_gui',
                'open_port', 'su'):
            self.assertTrue(mocked, '{} was not called'.format(mocked))

    def test_start_improv(self):
        test_backend = backend.Backend(config=self.alwaysTrue)
        test_backend.start()
        for mocked in (
                'service_control', 'start_improv', 'start_gui',
                'open_port', 'su'):
            self.assertTrue(mocked, '{} was not called'.format(mocked))

    def test_stop(self):
        test_backend = backend.Backend(config=self.alwaysFalse)
        test_backend.stop()
        for mocked in ('service_control', 'su'):
            self.assertTrue(mocked, '{} was not called'.format(mocked))


class TestBackendUtils(unittest.TestCase):

    def test_same_config(self):
        test_backend = backend.Backend(
            config={'sandbox': False, 'staging': False},
            prev_config={'sandbox': False, 'staging': False},
        )
        self.assertFalse(test_backend.different('sandbox'))
        self.assertFalse(test_backend.different('staging'))

    def test_different_config(self):
        test_backend = backend.Backend(
            config={'sandbox': False, 'staging': False},
            prev_config={'sandbox': True, 'staging': False},
        )
        self.assertTrue(test_backend.different('sandbox'))
        self.assertFalse(test_backend.different('staging'))
