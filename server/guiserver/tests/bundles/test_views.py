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

import datetime

import mock
from tornado import concurrent
from tornado.testing import(
    AsyncTestCase,
    ExpectLog,
    gen_test,
    LogTrapTestCase,
)
import yaml

from guiserver.bundles import views
from guiserver.tests import helpers


class ViewsTestMixin(object):
    """Base helpers and common tests for all the view tests.

    Subclasses must define a get_view() method returning the view function to
    be tested. Subclasses can also override the invalid_params and
    invalid_params_error attributes, used to test the view in the case the
    passed parameters are not valid.
    """

    invalid_params = {'No-such': 'parameter'}
    invalid_params_error = 'invalid request: invalid data parameters'

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
        expected_log = 'deployer: unauthorized access: no user logged in'
        with ExpectLog('', expected_log, required=True):
            response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'unauthorized access: no user logged in',
        }
        self.assertEqual(expected_response, response)
        # The Deployer methods have not been called.
        self.assertEqual(0, len(self.deployer.mock_calls))

    @gen_test
    def test_invalid_parameters(self):
        # An error response is returned if the parameters in the request are
        # not valid.
        request = self.make_view_request(params=self.invalid_params)
        expected_log = 'deployer: {}'.format(self.invalid_params_error)
        with ExpectLog('', expected_log, required=True):
            response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': self.invalid_params_error,
        }
        self.assertEqual(expected_response, response)
        # The Deployer methods have not been called.
        self.assertEqual(0, len(self.deployer.mock_calls))


class TestImportBundleV3(
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
    def test_no_name_failure(self):
        # An error response is returned if the requested bundle name is not
        # provided and the YAML contents include multiple bundles
        params = {'YAML': 'bundle1: contents1\nbundle2: contents2'}
        request = self.make_view_request(params=params)
        response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: invalid data parameters: '
                     'no bundle name provided',
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
        # An error response is returned if the bundle is not well formed.
        params = {'Name': 'mybundle', 'YAML': 'mybundle: not valid'}
        request = self.make_view_request(params=params)
        response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: invalid bundle mybundle: '
                     'the bundle data is not well formed',
        }
        self.assertEqual(expected_response, response)
        # The Deployer methods have not been called.
        self.assertEqual(0, len(self.deployer.mock_calls))

    @gen_test
    def test_invalid_bundle_constraints(self):
        # An error response is returned if the bundle includes services with
        # unsupported constraints.
        params = {
            'Name': 'mybundle',
            'YAML': 'mybundle: {services: {django: {constraints: invalid=1}}}',
        }
        request = self.make_view_request(params=params)
        response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: invalid bundle mybundle: '
                     'unsupported constraints: invalid',
        }
        self.assertEqual(expected_response, response)
        # The Deployer methods have not been called.
        self.assertEqual(0, len(self.deployer.mock_calls))

    @gen_test
    def test_undeployable_bundle(self):
        # An error response is returned if the bundle cannot be imported in the
        # current Juju environment.
        params = {'Name': 'mybundle', 'YAML': 'mybundle: {services: {}}'}
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
            request.user, {'services': {}})

    @gen_test
    def test_success(self):
        # The response includes the deployment identifier.
        params = {'Name': 'mybundle', 'YAML': 'mybundle: {services: {}}'}
        request = self.make_view_request(params=params)
        # Set up the Deployer mock.
        self.deployer.validate.return_value = self.make_future(None)
        self.deployer.import_bundle.return_value = 42
        # Execute the view.
        response = yield self.view(request, self.deployer)
        expected_response = {'Response': {'DeploymentId': 42}}
        self.assertEqual(expected_response, response)
        # Ensure the Deployer methods have been correctly called.
        args = (request.user, {'services': {}})
        self.deployer.validate.assert_called_once_with(*args)
        args = (request.user, 'mybundle', {'services': {}}, None)
        self.deployer.import_bundle.assert_called_once_with(*args)

    @gen_test
    def test_logging(self):
        # The beginning of the bundle import process is properly logged.
        params = {'Name': 'mybundle', 'YAML': 'mybundle: {services: {}}'}
        request = self.make_view_request(params=params)
        # Set up the Deployer mock.
        self.deployer.validate.return_value = self.make_future(None)
        self.deployer.import_bundle.return_value = 42
        # Execute the view.
        expected_log = "import_bundle: scheduling 'mybundle' deployment"
        with ExpectLog('', expected_log, required=True):
            yield self.view(request, self.deployer)

    # The following tests exercise views._validate_import_params directly.
    def test_no_name_success(self):
        # The process succeeds if the bundle name is not provided but the
        # YAML contents include just one bundle.
        params = {'YAML': 'mybundle: {services: {}}'}
        results = views._validate_import_params(params)
        expected = ('mybundle', {'services': {}}, None)
        self.assertEqual(expected, results)

    def test_id_provided(self):
        params = {'YAML': 'mybundle: {services: {}}',
                  'BundleID': '~jorge/wiki/3/smallwiki'}
        results = views._validate_import_params(params)
        expected = ('mybundle', {'services': {}}, '~jorge/wiki/3/smallwiki')
        self.assertEqual(expected, results)

    def test_id_and_name_provided(self):
        params = {'YAML': 'mybundle: {services: {}}',
                  'Name': 'mybundle',
                  'BundleID': '~jorge/wiki/3/smallwiki'}
        results = views._validate_import_params(params)
        expected = ('mybundle', {'services': {}}, '~jorge/wiki/3/smallwiki')
        self.assertEqual(expected, results)

    @gen_test
    def test_id_passed_to_deployer(self):
        params = {'YAML': 'mybundle: {services: {}}',
                  'Name': 'mybundle',
                  'BundleID': '~jorge/wiki/3/smallwiki'}
        request = self.make_view_request(params=params)
        # Set up the Deployer mock.
        self.deployer.validate.return_value = self.make_future(None)
        self.deployer.import_bundle.return_value = 42
        # Execute the view.
        yield self.view(request, self.deployer)
        # Ensure the Deployer methods have been correctly called.
        args = (request.user, {'services': {}})
        self.deployer.validate.assert_called_once_with(*args)
        args = (request.user, 'mybundle', {'services': {}},
                '~jorge/wiki/3/smallwiki')
        self.deployer.import_bundle.assert_called_once_with(*args)


class TestImportBundleV4(
        ViewsTestMixin, helpers.BundlesTestMixin, LogTrapTestCase,
        AsyncTestCase):

    def get_view(self):
        return views.import_bundle

    @gen_test
    def test_invalid_yaml(self):
        # An error response is returned if an invalid YAML encoded string is
        # passed.
        params = {'Name': 'bundle-name', 'Version': 4, 'YAML': 42}
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
    def test_invalid_bundle(self):
        # An error response is returned if the bundle is not well formed.
        params = {'YAML': 'not valid', 'Version': 4, 'BundleID': 'foo'}
        request = self.make_view_request(params=params)
        response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: invalid bundle bundle-v4: '
                     'the bundle data is not well formed',
        }
        self.assertEqual(expected_response, response)
        # The Deployer methods have not been called.
        self.assertEqual(0, len(self.deployer.mock_calls))

    @gen_test
    def test_invalid_bundle_constraints(self):
        # An error response is returned if the bundle includes services with
        # unsupported constraints.
        params = {
            'YAML': 'services: {django: {constraints: invalid=1}}',
            'Version': 4,
        }
        request = self.make_view_request(params=params)
        response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: invalid bundle bundle-v4: '
                     'unsupported constraints: invalid',
        }
        self.assertEqual(expected_response, response)
        # The Deployer methods have not been called.
        self.assertEqual(0, len(self.deployer.mock_calls))

    @gen_test
    def test_undeployable_bundle(self):
        # An error response is returned if the bundle cannot be imported in the
        # current Juju environment.
        params = {'Version': 4, 'YAML': 'services: {}'}
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
            request.user, {'services': {}})

    @gen_test
    def test_success(self):
        # The response includes the deployment identifier.
        params = {'BundleID': 'foo', 'Version': 4, 'YAML': 'services: {}'}
        request = self.make_view_request(params=params)
        # Set up the Deployer mock.
        self.deployer.validate.return_value = self.make_future(None)
        self.deployer.import_bundle.return_value = 42
        # Execute the view.
        response = yield self.view(request, self.deployer)
        expected_response = {'Response': {'DeploymentId': 42}}
        self.assertEqual(expected_response, response)
        # Ensure the Deployer methods have been correctly called.
        args = (request.user, {'services': {}})
        self.deployer.validate.assert_called_once_with(*args)
        args = (request.user, 'bundle-v4', {'services': {}}, 'foo')
        self.deployer.import_bundle.assert_called_once_with(*args)

    @gen_test
    def test_logging(self):
        # The beginning of the bundle import process is properly logged.
        params = {'BundleID': 'foo', 'Version': 4, 'YAML': 'services: {}'}
        request = self.make_view_request(params=params)
        # Set up the Deployer mock.
        self.deployer.validate.return_value = self.make_future(None)
        self.deployer.import_bundle.return_value = 42
        # Execute the view.
        expected_log = "import_bundle: scheduling 'bundle-v4' deployment"
        with ExpectLog('', expected_log, required=True):
            yield self.view(request, self.deployer)

    # The following tests exercise views._validate_import_params directly.
    def test_id_provided(self):
        params = {'YAML': 'services: {}',
                  'Version': 4,
                  'BundleID': '~jorge/wiki'}
        results = views._validate_import_params(params)
        expected = ('bundle-v4', {'services': {}}, '~jorge/wiki')
        self.assertEqual(expected, results)

    @gen_test
    def test_id_passed_to_deployer(self):
        params = {'YAML': 'services: {}',
                  'Version': 4,
                  'BundleID': '~jorge/wiki/3/smallwiki'}
        request = self.make_view_request(params=params)
        # Set up the Deployer mock.
        self.deployer.validate.return_value = self.make_future(None)
        self.deployer.import_bundle.return_value = 42
        # Execute the view.
        yield self.view(request, self.deployer)
        # Ensure the Deployer methods have been correctly called.
        args = (request.user, {'services': {}})
        self.deployer.validate.assert_called_once_with(*args)
        args = (request.user, 'bundle-v4', {'services': {}},
                '~jorge/wiki/3/smallwiki')
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

    @gen_test
    def test_logging(self):
        # The beginning of the bundle watch process is properly logged.
        request = self.make_view_request(params={'DeploymentId': 42})
        # Set up the Deployer mock.
        self.deployer.watch.return_value = 47
        # Execute the view.
        expected_log = 'watch: deployment 42 being observed by watcher 47'
        with ExpectLog('', expected_log, required=True):
            yield self.view(request, self.deployer)


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

    @gen_test
    def test_logging(self):
        # The watcher next request is properly logged.
        request = self.make_view_request(params={'WatcherId': 42})
        # Set up the Deployer mock.
        changes = ['change1', 'change2']
        self.deployer.next.return_value = self.make_future(changes)
        # Execute the view.
        expected_request_log = 'next: requested changes for watcher 42'
        expected_response_log = 'next: returning changes for watcher 42'
        with ExpectLog('', expected_request_log, required=True):
            with ExpectLog('', expected_response_log, required=True):
                yield self.view(request, self.deployer)


class TestCancel(
        ViewsTestMixin, helpers.BundlesTestMixin, LogTrapTestCase,
        AsyncTestCase):

    def get_view(self):
        return views.cancel

    @gen_test
    def test_invalid_deployment(self):
        # An error response is returned if the deployment identifier is not
        # valid.
        request = self.make_view_request(params={'DeploymentId': 42})
        # Set up the Deployer mock.
        self.deployer.cancel.return_value = 'bad wolf'
        # Execute the view.
        response = yield self.view(request, self.deployer)
        expected_response = {
            'Response': {},
            'Error': 'invalid request: bad wolf',
        }
        self.assertEqual(expected_response, response)
        # Ensure the Deployer methods have been correctly called.
        self.deployer.cancel.assert_called_once_with(42)

    @gen_test
    def test_success(self):
        # An empty response is returned if everything is ok.
        request = self.make_view_request(params={'DeploymentId': 42})
        # Set up the Deployer mock.
        self.deployer.cancel.return_value = None
        # Execute the view.
        response = yield self.view(request, self.deployer)
        self.assertEqual({'Response': {}}, response)
        # Ensure the Deployer methods have been correctly called.
        self.deployer.cancel.assert_called_once_with(42)

    @gen_test
    def test_logging(self):
        # The bundle cancellation is properly logged.
        request = self.make_view_request(params={'DeploymentId': 42})
        # Set up the Deployer mock.
        self.deployer.cancel.return_value = None
        # Execute the view.
        expected_log = 'cancel: deployment 42 cancelled'
        with ExpectLog('', expected_log, required=True):
            yield self.view(request, self.deployer)


class TestStatus(
        ViewsTestMixin, helpers.BundlesTestMixin, LogTrapTestCase,
        AsyncTestCase):

    invalid_params_error = 'invalid request: invalid data parameters: No-such'

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

    @gen_test
    def test_logging(self):
        # The status request is properly logged.
        request = self.make_view_request()
        # Set up the Deployer mock.
        self.deployer.status.return_value = []
        # Execute the view.
        expected_log = 'status: returning last changes'
        with ExpectLog('', expected_log, required=True):
            yield self.view(request, self.deployer)


class TestGetChangeSet(
        ViewsTestMixin, helpers.BundlesTestMixin, LogTrapTestCase,
        AsyncTestCase):

    invalid_params_error = (
        'invalid request: expected YAML or Token to be provided')

    def get_view(self):
        return views.get_change_set

    @gen_test
    def test_valid_yaml(self):
        # The change set is correctly returned when providing a YAML content.
        content = yaml.safe_dump({
            'services': {
                'django': {
                    'charm': 'cs:trusty/django-42',
                    'num_units': 1,
                },
            },
        })
        request = self.make_view_request(params={'YAML': content})
        expected_response = {
            'Response': {
                'ChangeSet': (
                    {'args': ['cs:trusty/django-42'],
                     'requires': [],
                     'id': 'addCharm-0',
                     'method': 'addCharm'},
                    {'args': ['cs:trusty/django-42', 'django', {}],
                     'requires': ['addCharm-0'],
                     'id': 'addService-1',
                     'method': 'deploy'},
                    {'args': ['$addService-1', 1, None],
                     'requires': ['addService-1'],
                     'id': 'addUnit-2',
                     'method': 'addUnit'},
                ),
            },
        }
        response = yield self.view(request, self.deployer)
        self.assertEqual(expected_response, response)

    @gen_test
    def test_invalid_bundle(self):
        # The validation errors are returned when providing an invalid bundle.
        request = self.make_view_request(params={'YAML': '42'})
        expected_response = {
            'Response': {'Errors': ['bundle does not appear to be a bundle']},
        }
        response = yield self.view(request, self.deployer)
        self.assertEqual(expected_response, response)

    @gen_test
    def test_not_yaml(self):
        # The validation errors are returned when providing an invalid YAML.
        request = self.make_view_request(params={'YAML': ':'})
        expected_response = {
            'Response': {
                'Errors': ['the provided bundle is not a valid YAML'],
            },
        }
        response = yield self.view(request, self.deployer)
        self.assertEqual(expected_response, response)


patch_time = mock.patch(
    'datetime.datetime',
    mock.Mock(**{'utcnow.return_value': datetime.datetime(2013, 11, 21, 21)}))


class TestSetChangeSet(
        ViewsTestMixin, helpers.BundlesTestMixin, LogTrapTestCase,
        AsyncTestCase):

    invalid_params_error = 'invalid request: bundle YAML not found'

    def get_view(self):
        return views.set_change_set

    @mock.patch('uuid.uuid4', mock.Mock(return_value=mock.Mock(hex='DEFACED')))
    @patch_time
    @gen_test
    def test_valid_yaml(self):
        # The change set is correctly returned when providing a YAML content.
        content = yaml.safe_dump({
            'services': {
                'django': {
                    'charm': 'cs:trusty/django-42',
                    'num_units': 0,
                },
            },
        })
        request = self.make_view_request(params={'YAML': content})
        expected_response = {
            'Response': {
                'Created': '2013-11-21T21:00:00Z',
                'Expires': '2013-11-21T21:02:00Z',
                'Token': 'DEFACED',
            },
        }
        response = yield self.view(request, self.deployer)
        self.assertEqual(expected_response, response)

        # Call GetChangeSet to retrieve the bundle changes.
        request = self.make_view_request(params={'Token': 'DEFACED'})
        expected_response = {
            'Response': {
                'ChangeSet': (
                    {'args': ['cs:trusty/django-42'],
                     'id': 'addCharm-0',
                     'method': 'addCharm',
                     'requires': []},
                    {'args': ['cs:trusty/django-42', 'django', {}],
                     'id': 'addService-1',
                     'method': 'deploy',
                     'requires': ['addCharm-0']},
                ),
            },
        }
        response = yield views.get_change_set(request, self.deployer)
        self.assertEqual(expected_response, response)
