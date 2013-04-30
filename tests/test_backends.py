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
            frozenset(('ppa:juju-gui/ppa',)), test_backend.repositories)
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
            frozenset(('ppa:juju-gui/ppa',)), test_backend.repositories)
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
            frozenset(('ppa:juju-gui/ppa',)), test_backend.repositories)
        self.assertEqual(
            frozenset(('haproxy.conf',)),
            test_backend.upstart_scripts)

    def test_go_backend(self):
        # Monkeypatch utils.CURRENT_DIR.
        base_dir = tempfile.mkdtemp()
        original_current_dir = utils.CURRENT_DIR
        utils.CURRENT_DIR = tempfile.mkdtemp(dir=base_dir)
        # Create a fake agent file.
        agent_path = os.path.join(base_dir, 'agent.conf')
        open(agent_path, 'w').close()
        test_backend = backend.Backend(
            config={'sandbox': False, 'staging': False})
        # Cleanup.
        utils.CURRENT_DIR = original_current_dir
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
            frozenset(('ppa:juju-gui/ppa',)), test_backend.repositories)
        self.assertEqual(
            frozenset(('haproxy.conf',)),
            test_backend.upstart_scripts)


class GotEmAllDict(dict):

    def __getitem__(self, key):
        return False


class TestBackendCommands(unittest.TestCase):

    def test_install(self):
        # Monkeypatch utils
        original_juju_dir = utils.JUJU_DIR
        original_sys_init_dir = backend.SYS_INIT_DIR
        temp_dir = tempfile.mkdtemp()
        utils.JUJU_DIR = temp_dir
        backend.SYS_INIT_DIR = temp_dir

        called = {}

        def mock_setup_apache():
            called['setup_apache'] = True
        original_setup_apache = utils.setup_apache
        utils.setup_apache = mock_setup_apache

        def mock_check_packages(*args):
            called['check_packages'] = True
            return False

        def mock_log(msg, *args):
            called['log'] = True

        test_backend = backend.Backend(
            config={'sandbox': False, 'staging': False},
            check_packages=mock_check_packages,
            log=mock_log)
        test_backend.install()
        self.assertTrue(called.get('check_packages'))
        self.assertTrue(called.get('setup_apache'))
        self.assertTrue(called.get('log'))

        # Cleanup.
        utils.setup_apache = original_setup_apache
        backend.SYS_INIT_DIR = original_sys_init_dir
        utils.JUJU_DIR = original_juju_dir
        shutil.rmtree(temp_dir)

    def test_start(self):
        called = {}

        def mock_start_gui(*args, **kwargs):
            called['start_gui'] = True
        original_start_gui = utils.start_gui
        utils.start_gui = mock_start_gui

        def mock_open_port(port):
            called['open_port'] = True
        original_open_port = charmhelpers.open_port
        charmhelpers.open_port = mock_open_port

        @contextmanager
        def mock_su(user):
            called['su'] = True
            yield None
        original_su = shelltoolbox.su
        shelltoolbox.su = mock_su

        def mock_service_control(service, action):
            called['service_control'] = True

        def mock_start_agent(cert_path):
            called['start_agent'] = True

        test_backend = backend.Backend(
            config=GotEmAllDict(),
            service_control=mock_service_control,
            start_agent=mock_start_agent)
        test_backend.start()
        self.assertTrue(called.get('service_control'))
        self.assertTrue(called.get('start_agent'))
        self.assertTrue(called.get('start_gui'))
        self.assertTrue(called.get('open_port'))
        self.assertTrue(called.get('su'))

        # Cleanup.
        shelltoolbox.su = original_su
        charmhelpers.open_port = original_open_port
        utils.setup_gui = original_start_gui


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
