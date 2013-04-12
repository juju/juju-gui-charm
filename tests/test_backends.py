import unittest

from backend import Backend


class StrategyClasses(unittest.TestCase):
    """
    As the number of configurations this charm supports increases it becomes
    desirable to move to Strategy pattern objects to implement features
    per backend. These tests insure the basic factory code works.
    """
    def test_get_python(self):
        config = {
            "apibackend": "python",
            "sandbox": False,
            "staging": True,
        }
        backend = Backend(config)
        self.assertIn("nginx", backend.dependencies)
        self.assertIn("haproxy", backend.dependencies)
        self.assertIn("curl", backend.debs)
        self.assertIn("openssl", backend.debs)
        self.assertIn('zookeeper', backend.staging_dependencies)
        self.assertIn('ppa:juju-gui/ppa', backend.repositories)

    def test_get_python_sandbox(self):
        config = {
            "apibackend": "python",
            "sandbox": True
        }
        backend = Backend(config)
        self.assertIn("nginx", backend.dependencies)
        self.assertNotIn('zookeeper', backend.staging_dependencies)



if __name__ == '__main__':
    unittest.main()
