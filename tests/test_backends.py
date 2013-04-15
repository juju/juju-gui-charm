import unittest

from backend import Backend
from contextlib import contextmanager

import charmhelpers
import tempfile
import utils

class TestBackends(unittest.TestCase):
    """
    As the number of configurations this charm supports increases it becomes
    desirable to move to Strategy pattern objects to implement features
    per backend. These tests insure the basic factory code works.
    """
    def backendNames(self, backend):
        return [b.__class__.__name__ for b in backend.backends]

    def test_get_python(self):
        config = {
            "sandbox": False,
            "staging": True,
        }
        backend = Backend(config)
        self.assertIn("nginx", backend.debs)
        self.assertIn("haproxy", backend.debs)
        self.assertIn("curl", backend.debs)
        self.assertIn("openssl", backend.debs)
        self.assertIn('zookeeper', backend.debs)
        self.assertIn('ppa:juju-gui/ppa', backend.repositories)
        self.assertIn('ImprovBackend', self.backendNames(backend))
        self.assertNotIn('PythonBackend', self.backendNames(backend))


    def test_get_python_sandbox(self):
        config = {
            "sandbox": True,
            "staging": True,
        }
        backend = Backend(config)
        self.assertIn("nginx", backend.debs)
        self.assertNotIn('zookeeper', backend.debs)
        self.assertNotIn('ImprovBackend', self.backendNames(backend))


    def test_allow_external_sources_false(self):
        # Turn off external software access and request a branch
        config = {
            "juju-gui-source": "lp:juju-gui",
            "allow-external-sources": False
        }
        def check_packages(*args):
            return None
        backend = Backend(config, check_packages=check_packages)
        with self.assertRaises(RuntimeError) as err:
            backend.install()
            self.assertTrue(str(err).startswith("Unable to fetch"))

