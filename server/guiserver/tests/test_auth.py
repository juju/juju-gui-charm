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

"""Tests for the Juju GUI server authentication management."""

import unittest

from guiserver import auth
from guiserver.tests import helpers


class TestUser(unittest.TestCase):

    def test_authenticated_repr(self):
        # An authenticated user is correctly represented.
        user = auth.User(
            username='the-doctor', password='bad-wolf', is_authenticated=True)
        expected = '<User: the-doctor (authenticated)>'
        self.assertEqual(expected, repr(user))

    def test_not_authenticated_repr(self):
        # A not authenticated user is correctly represented.
        user = auth.User(
            username='the-doctor', password='bad-wolf', is_authenticated=False)
        expected = '<User: the-doctor (not authenticated)>'
        self.assertEqual(expected, repr(user))

    def test_anonymous_repr(self):
        # An anonymous user is correctly represented.
        user = auth.User()
        expected = '<User: anonymous (not authenticated)>'
        self.assertEqual(expected, repr(user))


class AuthMiddlewareTestMixin(object):
    """Include tests for the AuthMiddleware.

    Subclasses must subclass one of the API test mixins in helpers.
    """

    def setUp(self):
        self.user = auth.User()
        self.auth = auth.AuthMiddleware(self.user, self.get_auth_backend())

    def assert_user(self, username, password, is_authenticated):
        """Ensure the current user reflects the given values."""
        user = self.user
        self.assertEqual(username, user.username)
        self.assertEqual(password, user.password)
        self.assertEqual(is_authenticated, user.is_authenticated)

    def test_login_request(self):
        # The authentication process starts if a log in request is processed.
        request = self.make_login_request(username='user', password='passwd')
        self.auth.process_request(request)
        self.assertTrue(self.auth.in_progress())
        self.assert_user('user', 'passwd', False)

    def test_login_success(self):
        # The user is logged in if the authentication process completes.
        request = self.make_login_request(username='user', password='passwd')
        self.auth.process_request(request)
        response = self.make_login_response()
        self.auth.process_response(response)
        self.assertFalse(self.auth.in_progress())
        self.assert_user('user', 'passwd', True)

    def test_login_failure(self):
        # The user is not logged in if the authentication process fails.
        request = self.make_login_request()
        self.auth.process_request(request)
        response = self.make_login_response(successful=False)
        self.auth.process_response(response)
        self.assertFalse(self.auth.in_progress())
        self.assert_user('', '', False)

    def test_request_mismatch(self):
        # The authentication fails if the request and response identifiers
        # don't match.
        request = self.make_login_request(
            request_id=42, username='user', password='passwd')
        self.auth.process_request(request)
        response = self.make_login_response(request_id=47)
        self.auth.process_response(response)
        self.assertTrue(self.auth.in_progress())
        self.assert_user('user', 'passwd', False)

    def test_multiple_auth_requests(self):
        # Only the last authentication request is taken into consideration.
        request1 = self.make_login_request(request_id=1)
        request2 = self.make_login_request(
            request_id=2, username='user2', password='passwd2')
        self.auth.process_request(request1)
        self.auth.process_request(request2)
        # The first response arrives.
        response = self.make_login_response(request_id=1)
        self.auth.process_response(response)
        # The user is still not autheticated and the auth is in progress.
        self.assertFalse(self.user.is_authenticated)
        self.assertTrue(self.auth.in_progress())
        # The second response arrives.
        response = self.make_login_response(request_id=2)
        self.auth.process_response(response)
        # The user logged in and the auth process completed.
        self.assert_user('user2', 'passwd2', True)
        self.assertFalse(self.auth.in_progress())


class TestGoAuthMiddleware(
        helpers.GoAPITestMixin, AuthMiddlewareTestMixin, unittest.TestCase):
    pass


class TestPythonAuthMiddleware(
        helpers.PythonAPITestMixin, AuthMiddlewareTestMixin,
        unittest.TestCase):
    pass


class BackendTestMixin(object):
    """Include tests for the authentication backends.

    Subclasses must subclass one of the API test mixins in helpers.
    """

    def setUp(self):
        self.backend = self.get_auth_backend()

    def test_get_request_id(self):
        # The request id is correctly returned.
        request = self.make_login_request(request_id=42)
        self.assertEqual(42, self.backend.get_request_id(request))

    def test_get_request_id_failure(self):
        # If the request id cannot be found, None is returned.
        self.assertIsNone(self.backend.get_request_id({}))

    def test_request_is_login(self):
        # True is returned if a log in request is passed.
        request = self.make_login_request()
        self.assertTrue(self.backend.request_is_login(request))

    def test_get_credentials(self):
        # The user name and password are returned parsing the log in request.
        request = self.make_login_request(username='user', password='passwd')
        username, password = self.backend.get_credentials(request)
        self.assertEqual('user', username)
        self.assertEqual('passwd', password)

    def test_login_succeeded(self):
        # True is returned if the log in succeeded.
        response = self.make_login_response()
        self.assertTrue(self.backend.login_succeeded(response))

    def test_login_failed(self):
        # False is returned if the log in failed.
        response = self.make_login_response(successful=False)
        self.assertFalse(self.backend.login_succeeded(response))


class TestGoBackend(
        helpers.GoAPITestMixin, BackendTestMixin, unittest.TestCase):

    def test_request_is_not_login(self):
        # False is returned if the passed data is not a log in request.
        requests = (
            {},
            {
                'RequestId': 1,
                'Type': 'INVALID',
                'Request': 'Login',
                'Params': {'AuthTag': 'user', 'Password': 'passwd'},
            },
            {
                'RequestId': 2,
                'Type': 'Admin',
                'Request': 'INVALID',
                'Params': {'AuthTag': 'user', 'Password': 'passwd'},
            },
            {
                'RequestId': 3,
                'Type': 'Admin',
                'Request': 'Login',
                'Params': {'Password': 'passwd'},
            },
        )
        for request in requests:
            is_login = self.backend.request_is_login(request)
            self.assertFalse(is_login, request)


class TestPythonBackend(
        helpers.PythonAPITestMixin, BackendTestMixin, unittest.TestCase):

    def test_request_is_not_login(self):
        # False is returned if the passed data is not a log in request.
        requests = (
            {},
            {
                'request_id': 42,
                'op': 'INVALID',
                'user': 'user',
                'password': 'passwd',
            },
            {
                'request_id': 42,
                'op': 'login',
                'password': 'passwd',
            },
            {
                'request_id': 42,
                'op': 'login',
                'user': 'user',
            },
        )
        for request in requests:
            is_login = self.backend.request_is_login(request)
            self.assertFalse(is_login, request)
