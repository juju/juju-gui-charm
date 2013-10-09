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

"""Tests for the deployment utility functions and objects."""

import unittest

import mock
from tornado import gen
from tornado.testing import(
    AsyncTestCase,
    ExpectLog,
    gen_test,
    LogTrapTestCase,
)

from guiserver import watchers
from guiserver.bundles import utils
from guiserver.tests import helpers


mock_time = mock.patch('time.time', mock.Mock(return_value=12345))


@mock_time
class TestCreateChange(unittest.TestCase):

    def test_status(self):
        # The change includes the deployment status.
        expected = {'DeploymentId': 0, 'Status': utils.STARTED, 'Time': 12345}
        obtained = utils.create_change(0, utils.STARTED)
        self.assertEqual(expected, obtained)

    def test_queue(self):
        # The change includes the deployment queue length.
        expected = {
            'DeploymentId': 1,
            'Status': utils.SCHEDULED,
            'Time': 12345,
            'Queue': 42,
        }
        obtained = utils.create_change(1, utils.SCHEDULED, queue=42)
        self.assertEqual(expected, obtained)

    def test_error(self):
        # The change includes a deployment error.
        expected = {
            'DeploymentId': 2,
            'Status': utils.COMPLETED,
            'Time': 12345,
            'Error': 'an error',
        }
        obtained = utils.create_change(2, utils.COMPLETED, error='an error')
        self.assertEqual(expected, obtained)

    def test_all_params(self):
        # The change includes all the parameters.
        expected = {
            'DeploymentId': 3,
            'Status': utils.COMPLETED,
            'Time': 12345,
            'Queue': 47,
            'Error': 'an error',
        }
        obtained = utils.create_change(
            3, utils.COMPLETED, queue=47, error='an error')
        self.assertEqual(expected, obtained)


class TestObserver(unittest.TestCase):

    def setUp(self):
        self.observer = utils.Observer()

    def assert_deployment(self, deployment_id):
        """Ensure the given deployment id is being observed.

        Also check that a watcher is associated with the given deployment id.
        Return the watcher.
        """
        deployments = self.observer.deployments
        self.assertIn(deployment_id, deployments)
        watcher = deployments[deployment_id]
        self.assertIsInstance(watcher, watchers.AsyncWatcher)
        return watcher

    def assert_watcher(self, watcher_id, deployment_id):
        """Ensure the given watcher id is associated with the deployment id."""
        watchers = self.observer.watchers
        self.assertIn(watcher_id, watchers)
        self.assertEqual(deployment_id, watchers[watcher_id])

    def test_initial(self):
        # A newly created observer does not contain deployments.
        self.assertEqual({}, self.observer.deployments)
        self.assertEqual({}, self.observer.watchers)

    def test_add_deployment(self):
        # A new deployment is correctly added to the observer.
        deployment_id = self.observer.add_deployment()
        self.assertEqual(1, len(self.observer.deployments))
        self.assert_deployment(deployment_id)

    def test_add_multiple_deployments(self):
        # Multiple deployments can be added to the observer.
        deployment1 = self.observer.add_deployment()
        deployment2 = self.observer.add_deployment()
        self.assertNotEqual(deployment1, deployment2)
        self.assertEqual(2, len(self.observer.deployments))
        watcher1 = self.assert_deployment(deployment1)
        watcher2 = self.assert_deployment(deployment2)
        self.assertNotEqual(watcher1, watcher2)

    def test_add_watcher(self):
        # A new watcher is correctly added to the observer.
        deployment_id = self.observer.add_deployment()
        watcher_id = self.observer.add_watcher(deployment_id)
        self.assertEqual(1, len(self.observer.watchers))
        self.assert_watcher(watcher_id, deployment_id)

    def test_add_multiple_watchers(self):
        # Multiple watchers can be added to the observer.
        deployment1 = self.observer.add_deployment()
        deployment2 = self.observer.add_deployment()
        watcher1 = self.observer.add_watcher(deployment1)
        watcher2 = self.observer.add_watcher(deployment2)
        self.assertNotEqual(watcher1, watcher2)
        self.assertEqual(2, len(self.observer.watchers))
        self.assert_watcher(watcher1, deployment1)
        self.assert_watcher(watcher2, deployment2)

    @mock_time
    def test_notify_scheduled(self):
        # It is possible to notify a new queue position for a deployment.
        deployment_id = self.observer.add_deployment()
        watcher = self.observer.deployments[deployment_id]
        self.observer.notify_position(deployment_id, 3)
        expected = {
            'DeploymentId': deployment_id,
            'Status': utils.SCHEDULED,
            'Time': 12345,
            'Queue': 3,
        }
        self.assertEqual(expected, watcher.getlast())
        self.assertFalse(watcher.closed)

    @mock_time
    def test_notify_started(self):
        # It is possible to notify that a deployment is (about to be) started.
        deployment_id = self.observer.add_deployment()
        watcher = self.observer.deployments[deployment_id]
        self.observer.notify_position(deployment_id, 0)
        expected = {
            'DeploymentId': deployment_id,
            'Status': utils.STARTED,
            'Time': 12345,
            'Queue': 0,
        }
        self.assertEqual(expected, watcher.getlast())
        self.assertFalse(watcher.closed)

    @mock_time
    def test_notify_cancelled(self):
        # It is possible to notify that a deployment has been cancelled.
        deployment_id = self.observer.add_deployment()
        watcher = self.observer.deployments[deployment_id]
        self.observer.notify_cancelled(deployment_id)
        expected = {
            'DeploymentId': deployment_id,
            'Status': utils.CANCELLED,
            'Time': 12345,
        }
        self.assertEqual(expected, watcher.getlast())
        self.assertTrue(watcher.closed)

    @mock_time
    def test_notify_completed(self):
        # It is possible to notify that a deployment is completed.
        deployment_id = self.observer.add_deployment()
        watcher = self.observer.deployments[deployment_id]
        self.observer.notify_completed(deployment_id)
        expected = {
            'DeploymentId': deployment_id,
            'Status': utils.COMPLETED,
            'Time': 12345,
        }
        self.assertEqual(expected, watcher.getlast())
        self.assertTrue(watcher.closed)

    @mock_time
    def test_notify_error(self):
        # It is possible to notify that an error occurred during a deployment.
        deployment_id = self.observer.add_deployment()
        watcher = self.observer.deployments[deployment_id]
        self.observer.notify_completed(deployment_id, error='bad wolf')
        expected = {
            'DeploymentId': deployment_id,
            'Status': utils.COMPLETED,
            'Time': 12345,
            'Error': 'bad wolf',
        }
        self.assertEqual(expected, watcher.getlast())
        self.assertTrue(watcher.closed)


class TestRequireAuthenticatedUser(
        helpers.BundlesTestMixin, LogTrapTestCase, AsyncTestCase):

    deployer = 'fake-deployer'

    def make_view(self):
        """Return a view to be used for tests.

        The resulting callable must be called with a request object as first
        argument and with self.deployer as second argument.
        """
        @gen.coroutine
        @utils.require_authenticated_user
        def myview(request, deployer):
            """An example testing view."""
            self.assertEqual(self.deployer, deployer)
            raise utils.response(info='ok')
        return myview

    @gen_test
    def test_authenticated(self):
        # The view is executed normally if the user is authenticated.
        view = self.make_view()
        request = self.make_view_request(is_authenticated=True)
        response = yield view(request, self.deployer)
        self.assertEqual({'Response': 'ok'}, response)

    @gen_test
    def test_not_authenticated(self):
        # The view returns an error response if the user is not authenticated.
        view = self.make_view()
        request = self.make_view_request(is_authenticated=False)
        response = yield view(request, self.deployer)
        expected = {
            'Response': {},
            'Error': 'unauthorized access: no user logged in',
        }
        self.assertEqual(expected, response)

    def test_wrap(self):
        # The decorated view looks like the wrapped function.
        view = self.make_view()
        self.assertEqual('myview', view.__name__)
        self.assertEqual('An example testing view.', view.__doc__)


class TestResponse(LogTrapTestCase, unittest.TestCase):

    def assert_response(self, expected, response):
        """Ensure the given gen.Return instance contains the expected response.
        """
        self.assertIsInstance(response, gen.Return)
        self.assertEqual(expected, response.value)

    def test_empty(self):
        # An empty response is correctly generated.
        expected = {'Response': {}}
        response = utils.response()
        self.assert_response(expected, response)

    def test_success(self):
        # A success response is correctly generated.
        expected = {'Response': {'foo': 'bar'}}
        response = utils.response({'foo': 'bar'})
        self.assert_response(expected, response)

    def test_failure(self):
        # A failure response is correctly generated.
        expected = {'Error': 'an error occurred', 'Response': {}}
        response = utils.response(error='an error occurred')
        self.assert_response(expected, response)

    def test_log_failure(self):
        # An error log is written when a failure response is generated.
        with ExpectLog('', 'deployer: an error occurred', required=True):
            utils.response(error='an error occurred')