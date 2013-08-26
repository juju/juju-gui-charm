# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2013 Canonical Ltd.
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

"""Tests for the bundles support blocking functions and objects."""

from contextlib import contextmanager
import os
import shutil
import tempfile
import unittest

import mock

from guiserver.bundles import blocking
from guiserver.tests import helpers


@mock.patch('deployer.env.go.EnvironmentClient')
class TestEnvironment(unittest.TestCase):

    endpoint = 'wss://api.example.com:17070'
    password = 'Secret!'

    def setUp(self):
        self.env = blocking._Environment(self.endpoint, self.password)

    def test_connect(self, mock_client):
        # The environment uses the provided endpoint and password to connect
        # to the Juju API server.
        self.env.connect()
        mock_client.assert_called_once_with(self.endpoint)
        mock_client().login.assert_called_once_with(self.password)

    def test_multiple_connections(self, mock_client):
        # The environment does not attempt a second connection if it is already
        # connected to the API backend.
        self.env.connect()
        self.env.connect()
        self.assertEqual(1, mock_client.call_count)

    def test_close(self, mock_client):
        # The client attribute is set to None when the connection is closed.
        self.env.connect()
        self.env.close()
        self.assertIsNone(self.env.client)

    def test_deploy(self, mock_client):
        # The environment uses the API to deploy charms.
        self.env.connect()
        config = {'foo': 'bar'}
        constraints = {'cpu': 4}
        # Deploy a service: the last two arguments (force_machine and repo) are
        # ignored.
        self.env.deploy(
            'myservice', 'cs:precise/service-42', config=config,
            constraints=constraints, num_units=2, force_machine=1, repo='/tmp')
        mock_client().deploy.assert_called_once_with(
            'myservice', 'cs:precise/service-42', config=config,
            constraints=constraints, num_units=2)


class DeployerFunctionsTestMixin(helpers.BundlesTestMixin):
    """Base set up for the functions that make use of the juju-deployer."""

    apiurl = 'wss://api.example.com:17070'
    password = 'Secret!'

    def setUp(self):
        self.name, self.bundle = self.get_name_and_bundle()

    def check_environment_life(self, mock_environment):
        """Check the calls executed on the given mock environment.

        Ensure that, in order to retrieve the list of currently deployed
        services, the environment is instantiated, connected, env.status is
        called and then the connection is closed.
        """
        mock_environment.assert_called_once_with(self.apiurl, self.password)
        mock_env_instance = mock_environment()
        mock_env_instance.connect.assert_called_once_with()
        mock_env_instance.status.assert_called_once_with()
        mock_env_instance.close.assert_called_once_with()

    @contextmanager
    def assert_overlapping_services(self, mock_environment):
        """Ensure a ValueError is raised in the context manager block.

        The given mock environment object is set up so that its status
        simulates an existing service. The name of this service overlaps with
        the name of one of the services in the bundle.
        """
        mock_env_instance = mock_environment()
        mock_env_instance.status.return_value = {'services': {'mysql': {}}}
        # Ensure a ValueError is raised by the code in the context block.
        with self.assertRaises(ValueError) as context_manager:
            yield
        # The error reflects the overlapping service name.
        error = str(context_manager.exception)
        self.assertEqual('service(s) already in the environment: mysql', error)
        # Even if an error occurs, the environment connection is closed.
        mock_env_instance.close.assert_called_once_with()


@mock.patch('guiserver.bundles.blocking._Environment')
class TestValidate(DeployerFunctionsTestMixin, unittest.TestCase):

    def test_validation(self, mock_environment):
        # The validation is correctly run.
        blocking.validate(self.apiurl, self.password, self.bundle)
        # The environment is correctly instantiated and used.
        self.check_environment_life(mock_environment)

    def test_overlapping_services(self, mock_environment):
        # The validation fails if the bundle includes a service name already
        # present in the Juju environment.
        with self.assert_overlapping_services(mock_environment):
            blocking.validate(self.apiurl, self.password, self.bundle)


@mock.patch('guiserver.bundles.blocking._Environment')
class TestImportBundle(DeployerFunctionsTestMixin, unittest.TestCase):

    @contextmanager
    def patch_juju_home(self):
        """Patch the value used by the bundle importer as Juju home."""
        base_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base_dir)
        juju_home = os.path.join(base_dir, 'juju-home')
        with mock.patch('guiserver.bundles.blocking.JUJU_HOME', juju_home):
            yield juju_home

    @mock.patch('guiserver.bundles.blocking.Importer')
    def test_importing_bundle(self, mock_importer, mock_environment):
        # The juju-deployer importer is correctly set up and run.
        with self.patch_juju_home():
            blocking.import_bundle(
                self.apiurl, self.password, self.name, self.bundle)
        # The environment is correctly instantiated and used.
        self.check_environment_life(mock_environment)
        # The importer is correctly instantiated.
        self.assertEqual(1, mock_importer.call_count)
        importer_args = mock_importer.call_args[0]
        self.assertEqual(3, len(importer_args))
        env, deployment, options = importer_args
        # The first argument passed to the importer is the environment.
        self.assertIs(mock_environment(), env)
        # The second argument is the deployment object.
        self.assertIsInstance(deployment, blocking.Deployment)
        self.assertEqual(self.name, deployment.name)
        self.assertEqual(self.bundle, deployment.data)
        # The third and last argument is the options object.
        self.assertIs(blocking.IMPORTER_OPTIONS, options)
        # The importer is started.
        mock_importer().run.assert_called_once_with()

    def test_overlapping_services(self, mock_environment):
        # The import fails if the bundle includes a service name already
        # present in the Juju environment.
        with self.assert_overlapping_services(mock_environment):
            with self.patch_juju_home():
                blocking.import_bundle(
                    self.apiurl, self.password, self.name, self.bundle)

    @mock.patch('guiserver.bundles.blocking.Importer')
    def test_juju_home(self, mock_importer, mock_environment):
        # A customized Juju home is created and used during the import process.
        with self.patch_juju_home() as juju_home:
            assert not os.path.isdir(juju_home), 'directory should not exist'
            # Ensure JUJU_HOME is included in the context when the Importer
            # instance is run.
            run = lambda: self.assertEqual(juju_home, os.getenv('JUJU_HOME'))
            mock_importer().run = run
            blocking.import_bundle(
                self.apiurl, self.password, self.name, self.bundle)
        # The JUJU_HOME directory has been created.
        self.assertTrue(os.path.isdir(juju_home))
