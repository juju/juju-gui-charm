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
            frozenset(('ppa:juju-gui/ppa',)), test_backend.repositories)
        self.assertEqual(
            frozenset(('haproxy.conf',)),
            test_backend.upstart_scripts)


class GotEmAllDict(dict):
    """A dictionary that always returns the same default value for any key."""

    def __init__(self, default):
        self.default = default
        super(GotEmAllDict, self).__init__()

    def __getitem__(self, key):
        return self.default

    def get(self, key, default=None):
        return self.default


class TestBackendCommands(unittest.TestCase):

    def setUp(self):
        self.called = {}

        def mock_setup_apache():
            self.called['setup_apache'] = True
        self.orig_setup_apache = utils.setup_apache
        utils.setup_apache = mock_setup_apache

        def mock_fetch_api(juju_api_branch):
            self.called['fetch_api'] = True
        self.orig_fetch_api = utils.fetch_api
        utils.fetch_api = mock_fetch_api

        def mock_fetch_gui(juju_gui_source, logpath):
            self.called['fetch_gui'] = True
        self.orig_fetch_gui = utils.fetch_gui
        utils.fetch_gui = mock_fetch_gui

        def mock_setup_gui(release_tarball):
            self.called['setup_gui'] = True
        self.orig_setup_gui = utils.setup_gui
        utils.setup_gui = mock_setup_gui

        def mock_save_or_create_certificates(
                ssl_cert_path, ssl_cert_contents, ssl_key_contents):
            self.called['save_or_create_certificates'] = True
        self.orig_save_or_create_certs = utils.save_or_create_certificates
        utils.save_or_create_certificates = mock_save_or_create_certificates

        def mock_find_missing_packages(*args):
            self.called['find_missing_packages'] = True
            return False
        self.orig_find_missing_packages = utils.find_missing_packages
        utils.find_missing_packages = mock_find_missing_packages

        def mock_prime_npm_cache(npm_cache_url):
            self.called['prime_npm_cache'] = True
        self.orig_prime_npm_cache = utils.prime_npm_cache
        utils.prime_npm_cache = mock_prime_npm_cache

        def mock_get_npm_cache_archive_url(Launchpad=''):
            self.called['get_npm_cache_archive_url'] = True
        self.orig_get_npm_cache_archive_url = utils.get_npm_cache_archive_url
        utils.get_npm_cache_archive_url = mock_get_npm_cache_archive_url

        def mock_start_gui(*args, **kwargs):
            self.called['start_gui'] = True
        self.orig_start_gui = utils.start_gui
        utils.start_gui = mock_start_gui

        def mock_start_agent(cert_path):
            self.called['start_agent'] = True
        self.orig_start_agent = utils.start_agent
        utils.start_agent = mock_start_agent

        def mock_start_improv(stage_env, cert_path):
            self.called['start_improv'] = True
        self.orig_start_improv = utils.start_improv
        utils.start_improv = mock_start_improv

        def mock_log(msg, *args):
            self.called['log'] = True
        self.orig_log = charmhelpers.log
        charmhelpers.log = mock_log

        def mock_open_port(port):
            self.called['open_port'] = True
        self.orig_open_port = charmhelpers.open_port
        charmhelpers.open_port = mock_open_port

        def mock_service_control(service, action):
            self.called['service_control'] = True
        self.orig_service_control = charmhelpers.service_control
        charmhelpers.service_control = mock_service_control

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
        charmhelpers.service_control = self.orig_service_control
        charmhelpers.open_port = self.orig_open_port
        charmhelpers.log = self.orig_log
        utils.start_improv = self.orig_start_improv
        utils.start_agent = self.orig_start_agent
        utils.start_gui = self.orig_start_gui
        utils.get_npm_cache_archive_url = self.orig_get_npm_cache_archive_url
        utils.prime_npm_cache = self.orig_prime_npm_cache
        utils.find_missing_packages = self.orig_find_missing_packages
        utils.save_or_create_certificates = self.orig_save_or_create_certs
        utils.setup_gui = self.orig_setup_gui
        utils.fetch_gui = self.orig_fetch_gui
        utils.fetch_api = self.orig_fetch_api
        utils.setup_apache = self.orig_setup_apache

    def test_install_python(self):
        test_backend = backend.Backend(config=GotEmAllDict(False))
        test_backend.install()
        for mocked in (
                'find_missing_packages', 'setup_apache', 'fetch_api', 'log'):
            self.assertTrue(mocked, '{} was not called'.format(mocked))

    def test_install_improv(self):
        test_backend = backend.Backend(config=GotEmAllDict(True))
        test_backend.install()
        for mocked in (
                'find_missing_packages', 'setup_apache', 'fetch_api', 'log'):
            self.assertTrue(mocked, '{} was not called'.format(mocked))

    def test_start_agent(self):
        test_backend = backend.Backend(config=GotEmAllDict(False))
        test_backend.start()
        for mocked in ('service_control', 'start_agent', 'start_gui',
                'open_port', 'su'):
            self.assertTrue(mocked, '{} was not called'.format(mocked))

    def test_start_improv(self):
        test_backend = backend.Backend(config=GotEmAllDict(True))
        test_backend.start()
        for mocked in ('service_control', 'start_improv', 'start_gui',
                'open_port', 'su'):
            self.assertTrue(mocked, '{} was not called'.format(mocked))

    def test_stop(self):
        test_backend = backend.Backend(config=GotEmAllDict(False))
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
