import os
import shutil
import tempfile
import unittest

from backend import Backend
# Import the utils package for monkey patching.
import utils


def get_mixin_names(backend):
    return frozenset(b.__class__.__name__ for b in backend.mixins)


class TestBackends(unittest.TestCase):
    """
    As the number of configurations this charm supports increases it becomes
    desirable to move to Strategy pattern objects to implement features
    per backend. These tests insure the basic factory code works.
    """

    def test_staging_backend(self):
        backend = Backend(config={'sandbox': False, 'staging': True})
        mixin_names = get_mixin_names(backend)
        self.assertEqual(frozenset(('ImprovBackend',)), mixin_names)
        self.assertEqual(
            frozenset(('apache2', 'curl', 'haproxy', 'openssl', 'zookeeper')),
            backend.debs)
        self.assertEqual(
            frozenset(('ppa:juju-gui/ppa',)), backend.repositories)
        self.assertEqual(frozenset(('haproxy.conf',)), backend.upstart_scripts)

    def test_sandbox_backend(self):
        backend = Backend(config={'sandbox': True, 'staging': False})
        mixin_names = get_mixin_names(backend)
        self.assertEqual(frozenset(('SandboxBackend',)), mixin_names)
        self.assertEqual(
            frozenset(('apache2', 'curl', 'haproxy', 'openssl')),
            backend.debs)
        self.assertEqual(
            frozenset(('ppa:juju-gui/ppa',)), backend.repositories)
        self.assertEqual(frozenset(('haproxy.conf',)), backend.upstart_scripts)

    def test_python_backend(self):
        backend = Backend(config={'sandbox': False, 'staging': False})
        mixin_names = get_mixin_names(backend)
        self.assertEqual(frozenset(('PythonBackend',)), mixin_names)
        self.assertEqual(
            frozenset(('apache2', 'curl', 'haproxy', 'openssl')),
            backend.debs)
        self.assertEqual(
            frozenset(('ppa:juju-gui/ppa',)), backend.repositories)
        self.assertEqual(frozenset(('haproxy.conf',)), backend.upstart_scripts)

    def test_go_backend(self):
        # Monkeypatch utils.CURRENT_DIR.
        base_dir = tempfile.mkdtemp()
        original_current_dir = utils.CURRENT_DIR
        utils.CURRENT_DIR = tempfile.mkdtemp(dir=base_dir)
        # Create a fake agent file.
        agent_path = os.path.join(base_dir, 'agent.conf')
        open(agent_path, 'w').close()
        backend = Backend(config={'sandbox': False, 'staging': False})
        # Cleanup.
        utils.CURRENT_DIR = original_current_dir
        shutil.rmtree(base_dir)
        # Tests
        mixin_names = get_mixin_names(backend)
        self.assertEqual(frozenset(('GoBackend',)), mixin_names)
        self.assertEqual(
            frozenset(('apache2', 'curl', 'haproxy', 'openssl')),
            backend.debs)
        self.assertEqual(
            frozenset(('ppa:juju-gui/ppa',)), backend.repositories)
        self.assertEqual(frozenset(('haproxy.conf',)), backend.upstart_scripts)

    def test_same_config(self):
        backend = Backend(
            config={'sandbox': False, 'staging': False},
            prev_config={'sandbox': False, 'staging': False},
        )
        self.assertFalse(backend.different('sandbox'))
        self.assertFalse(backend.different('staging'))

    def test_different_config(self):
        backend = Backend(
            config={'sandbox': False, 'staging': False},
            prev_config={'sandbox': True, 'staging': False},
        )
        self.assertTrue(backend.different('sandbox'))
        self.assertFalse(backend.different('staging'))
