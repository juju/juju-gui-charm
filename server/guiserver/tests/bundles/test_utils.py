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

"""Tests for the deployment utility functions."""

import unittest

from tornado import gen
from tornado.testing import(
    AsyncTestCase,
    ExpectLog,
    gen_test,
    LogTrapTestCase,
)

from guiserver.bundles import utils
from guiserver.tests import helpers


class TestChange(unittest.TestCase):

    def test_status(self):
        # The change includes the deployment status.
        expected = {'DeploymentId': 0, 'Status': 'started'}
        obtained = utils.change(0, 'started')
        self.assertEqual(expected, obtained)

    def test_queue(self):
        # The change includes the deployment queue length.
        expected = {'DeploymentId': 1, 'Status': 'scheduled', 'Queue': 42}
        obtained = utils.change(1, 'scheduled', queue=42)
        self.assertEqual(expected, obtained)

    def test_error(self):
        # The change includes a deployment error.
        expected = {
            'DeploymentId': 2,
            'Status': 'completed',
            'Error': 'an error',
        }
        obtained = utils.change(2, 'completed', error='an error')
        self.assertEqual(expected, obtained)

    def test_all_params(self):
        # The change includes all the parameters.
        expected = {
            'DeploymentId': 3,
            'Status': 'completed',
            'Queue': 47,
            'Error': 'an error',
        }
        obtained = utils.change(3, 'completed', queue=47, error='an error')
        self.assertEqual(expected, obtained)


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
            'Error': 'unauthorized access: unknown user',
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
