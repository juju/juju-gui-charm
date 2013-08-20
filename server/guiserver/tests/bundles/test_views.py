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

"""Tests for the bundle deployment views."""

import mock
from tornado import concurrent
from tornado.testing import(
    AsyncTestCase,
    ExpectLog,
    gen_test,
    LogTrapTestCase,
)

from guiserver.bundles import views
from guiserver.tests import helpers


class ViewsTestMixin(object):
    """Base helpers and common tests for all the view tests.

    Subclasses must define a get_view() method returning the view function to
    be tested. Subclasses can also override the invalid_params attribute, used
    to test the view in the case the passed parameters are not valid.
    """

    invalid_params = {'No-such': 'parameter'}

    def setUp(self):
        super(ViewsTestMixin, self).setUp()
        self.view = self.get_view()
        self.deployer = mock.Mock()

    def make_future(self, result):
        """Create and return a Future containing the given result."""
        future = concurrent.Future()
        future.set_result(result)
        return future

    @gen_test
    def test_not_authenticated(self):
        # An error response is returned if the user is not authenticated.
        request = self.make_view_request(is_authenticated=False)
        expected_log = 'deployer: unauthorized access: unknown user'
        with ExpectLog('', expected_log, required=True):
            response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'unauthorized access: unknown user',
        }
        self.assertEqual(expected_response, response)
        # The Deployer methods have not been called.
        self.assertEqual(0, len(self.deployer.mock_calls))

    @gen_test
    def test_invalid_parameters(self):
        # An error response is returned if the parameters in the request are
        # not valid.
        request = self.make_view_request(params=self.invalid_params)
        expected_log = 'deployer: invalid request: invalid data parameters'
        with ExpectLog('', expected_log, required=True):
            response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: invalid data parameters',
        }
        self.assertEqual(expected_response, response)
        # The Deployer methods have not been called.
        self.assertEqual(0, len(self.deployer.mock_calls))


class TestImportBundle(
        ViewsTestMixin, helpers.BundlesTestMixin, LogTrapTestCase,
        AsyncTestCase):

    def get_view(self):
        return views.import_bundle

    @gen_test
    def test_invalid_yaml(self):
        # An error response is returned if an invalid YAML encoded string is
        # passed.
        params = {'Name': 'bundle-name', 'YAML': 42}
        request = self.make_view_request(params=params)
        response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: invalid YAML contents: '
                     "'int' object has no attribute 'read'",
        }
        self.assertEqual(expected_response, response)
        # The Deployer methods have not been called.
        self.assertEqual(0, len(self.deployer.mock_calls))

    @gen_test
    def test_bundle_not_found(self):
        # An error response is returned if the requested bundle name is not
        # found in the bundle YAML contents.
        params = {'Name': 'no-such-bundle', 'YAML': 'mybundle: mycontents'}
        request = self.make_view_request(params=params)
        response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: bundle no-such-bundle not found',
        }
        self.assertEqual(expected_response, response)
        # The Deployer methods have not been called.
        self.assertEqual(0, len(self.deployer.mock_calls))

    @gen_test
    def test_invalid_bundle(self):
        # An error response is returned if the bundle cannot be imported in the
        # current Juju environment.
        params = {'Name': 'mybundle', 'YAML': 'mybundle: mycontents'}
        request = self.make_view_request(params=params)
        # Simulate an error returned by the Deployer validate method.
        self.deployer.validate.return_value = self.make_future('an error')
        # Execute the view.
        response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: an error',
        }
        self.assertEqual(expected_response, response)
        # The Deployer validate method has been called.
        self.deployer.validate.assert_called_once_with(
            request.user, 'mybundle', 'mycontents')

    @gen_test
    def test_success(self):
        # The response includes the deployment identifier.
        params = {'Name': 'mybundle', 'YAML': 'mybundle: mycontents'}
        request = self.make_view_request(params=params)
        # Set up the Deployer mock.
        self.deployer.validate.return_value = self.make_future(None)
        self.deployer.import_bundle.return_value = 42
        # Execute the view.
        response = yield self.view(request, self.deployer)
        expected_response = {'Response': {'DeploymentId': 42}}
        self.assertEqual(expected_response, response)
        # Ensure the Deployer methods have been correctly called.
        args = (request.user, 'mybundle', 'mycontents')
        self.deployer.validate.assert_called_once_with(*args)
        self.deployer.import_bundle.assert_called_once_with(*args)


class TestWatch(
        ViewsTestMixin, helpers.BundlesTestMixin, LogTrapTestCase,
        AsyncTestCase):

    def get_view(self):
        return views.watch

    @gen_test
    def test_deployment_not_found(self):
        # An error response is returned if the deployment identifier is not
        # valid.
        request = self.make_view_request(params={'DeploymentId': 42})
        # Set up the Deployer mock.
        self.deployer.watch.return_value = None
        # Execute the view.
        response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: deployment not found',
        }
        self.assertEqual(expected_response, response)
        # Ensure the Deployer methods have been correctly called.
        self.deployer.watch.assert_called_once_with(42)

    @gen_test
    def test_success(self):
        # The response includes the watcher identifier.
        request = self.make_view_request(params={'DeploymentId': 42})
        # Set up the Deployer mock.
        self.deployer.watch.return_value = 47
        # Execute the view.
        response = yield self.view(request, self.deployer)
        expected_response = {'Response': {'WatcherId': 47}}
        self.assertEqual(expected_response, response)
        # Ensure the Deployer methods have been correctly called.
        self.deployer.watch.assert_called_once_with(42)


class TestNext(
        ViewsTestMixin, helpers.BundlesTestMixin, LogTrapTestCase,
        AsyncTestCase):

    def get_view(self):
        return views.next

    @gen_test
    def test_invalid_watcher_identifier(self):
        # An error response is returned if the watcher identifier is not valid.
        request = self.make_view_request(params={'WatcherId': 42})
        # Set up the Deployer mock.
        self.deployer.next.return_value = self.make_future(None)
        # Execute the view.
        response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: invalid watcher identifier',
        }
        self.assertEqual(expected_response, response)
        # Ensure the Deployer methods have been correctly called.
        self.deployer.next.assert_called_once_with(42)

    @gen_test
    def test_success(self):
        # The response includes the deployment changes.
        request = self.make_view_request(params={'WatcherId': 42})
        # Set up the Deployer mock.
        changes = ['change1', 'change2']
        self.deployer.next.return_value = self.make_future(changes)
        # Execute the view.
        response = yield self.view(request, self.deployer)
        expected_response = {'Response': {'Changes': changes}}
        self.assertEqual(expected_response, response)
        # Ensure the Deployer methods have been correctly called.
        self.deployer.next.assert_called_once_with(42)


class TestStatus(
        ViewsTestMixin, helpers.BundlesTestMixin, LogTrapTestCase,
        AsyncTestCase):

    def get_view(self):
        return views.status

    @gen_test
    def test_success(self):
        # The response includes the watcher identifier.
        request = self.make_view_request()
        # Set up the Deployer mock.
        last_changes = ['change1', 'change2']
        self.deployer.status.return_value = last_changes
        # Execute the view.
        response = yield self.view(request, self.deployer)
        expected_response = {'Response': {'LastChanges': last_changes}}
        self.assertEqual(expected_response, response)
        # Ensure the Deployer methods have been correctly called.
        self.deployer.status.assert_called_once_with()
