import unittest

from backend import Backend


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
        self.assertIn("apache2", backend.debs)
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
            "staging": False,
        }
        backend = Backend(config)
        self.assertIn("apache2", backend.debs)
        self.assertNotIn('zookeeper', backend.debs)
        self.assertNotIn('ImprovBackend', self.backendNames(backend))
