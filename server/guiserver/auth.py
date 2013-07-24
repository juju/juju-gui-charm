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

"""Juju GUI server authentication management.

This module includes the pieces required to process user authentication:

    - User: a simple data structure representing a logged in or anonymous user;
    - authentication backends (GoBackend and PythonBackend): any object
      implementing the following interface:
        - get_request_id(data);
        - request_is_login(data);
        - get_credentials(data);
        - login_succeeded(data).
      The only purpose of auth backends is to provide the logic to parse
      requests' data based on the API implementation currently in use. Backends
      don't know anything about the authentication process or the current user,
      and are not intended to store state: one backend (the one suitable for
      the current API implementation) is instantiated once when the application
      is bootstrapped and used as a singleton by all WebSocket requests;
    - AuthMiddleware: process authentication requests and responses, using
      the backend to parse the WebSocket messages, logging in the current user
      if the authentication succeeds.
"""


class User(object):
    """The current WebSocket user."""

    def __init__(self, username='', password='', is_authenticated=False):
        self.is_authenticated = is_authenticated
        # YAGNI: the username/password attributes are not required for now, but
        # they can help to handle the HA story, i.e. in the process of
        # re-authenticating to the API after switching from one Juju state/API
        # server to another.
        self.username = username
        self.password = password

    def __repr__(self):
        auth_repr = 'authenticated' if self.is_authenticated else 'anonymous'
        return '<User: {!r} {}>'.format(self.username, auth_repr)


class AuthMiddleware(object):
    """Handle user authentication.

    This class handles the process of authenticating the provided user using
    the given auth backend. Note that, since the GUI just disconnects when the
    user logs out, there is no need to handle the log out process.
    """

    def __init__(self, user, backend):
        self._user = user
        self._backend = backend
        self._request_id = None

    def in_progress(self):
        """Return True if the authentication is in progress, False otherwise.
        """
        return self._request_id is not None

    def process_request(self, data):
        """Parse the WebSocket data arriving from the client.

        Start the authentication process if data represents a log in request
        performed by the GUI user.
        """
        backend = self._backend
        request_id = backend.get_request_id(data)
        if request_id and backend.request_is_login(data):
            self._request_id = request_id
            credentials = backend.get_credentials(data)
            self._user.username, self._user.password = credentials

    def process_response(self, data):
        """Parse the WebSocket data arriving from the Juju API server.

        Complete the authentication process if data represents the response
        to a log in request previously initiated. Authenticate the user if
        the authentication succeeded.

        """
        request_id = self._backend.get_request_id(data)
        if request_id == self._request_id:
            logged_in = self._backend.login_succeeded(data)
            if logged_in:
                self._user.is_authenticated = True
            else:
                self._user.username = self._user.password = ''
            self._request_id = None


class GoBackend(object):
    """Authentication backend for the Juju Go API implementation.

    A login request looks like the following:

        {
            'RequestId': 42,
            'Type': 'Admin',
            'Request': 'Login',
            'Params': {'AuthTag': 'user-admin', 'Password': 'ADMIN-SECRET'},
        }

    Here is an example of a successful login response:

        {'RequestId': 42, 'Response': {}}

    A login failure response is like the following:

        {
            'RequestId': 42,
            'Error': 'invalid entity name or password',
            'ErrorCode': 'unauthorized access',
            'Response': {},
        }
    """

    def get_request_id(self, data):
        """Return the request identifier associated with the provided data."""
        return data.get('RequestId')

    def request_is_login(self, data):
        """Return True if data represents a log in request, False otherwise."""
        params = data.get('Params', {})
        return (
            data.get('Type') == 'Admin' and
            data.get('Request') == 'Login' and
            'AuthTag' in params and
            'Password' in params
        )

    def get_credentials(self, data):
        """Parse the provided log in data and return username and password."""
        params = data['Params']
        return params['AuthTag'], params['Password']

    def login_succeeded(self, data):
        """Return True if data represents a successful log in, False otherwise.
        """
        return 'Error' not in data


class PythonBackend(object):
    """Authentication backend for the Juju Python implementation.

    A login request looks like the following:

        {
            'request_id': 42,
            'op': 'login',
            'user': 'admin',
            'password': 'ADMIN-SECRET',
        }

    A successful login response includes these fields:

        {
            'request_id': 42,
            'op': 'login',
            'user': 'admin',
            'password': 'ADMIN-SECRET',
            'result': True,
        }

    A login failure response is like the following:

        {
            'request_id': 42,
            'op': 'login',
            'user': 'admin',
            'password': 'ADMIN-SECRET',
            'err': True,
        }
    """

    def get_request_id(self, data):
        """Return the request identifier associated with the provided data."""
        return data.get('request_id')

    def request_is_login(self, data):
        """Return True if data represents a log in request, False otherwise."""
        op = data.get('op')
        return (op == 'login') and ('user' in data) and ('password' in data)

    def get_credentials(self, data):
        """Parse the provided log in data and return username and password."""
        return data['user'], data['password']

    def login_succeeded(self, data):
        """Return True if data represents a successful log in, False otherwise.
        """
        return data.get('result') and not data.get('err')


def get_backend(apiversion):
    """Return the auth backend instance to use for the given API version."""
    backend_class = {'go': GoBackend, 'python': PythonBackend}[apiversion]
    return backend_class()
