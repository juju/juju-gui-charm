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

import mock
from tornado import gen
from tornado.testing import(
    AsyncTestCase,
    gen_test,
    LogTrapTestCase,
)

from guiserver import auth
from guiserver.bundles import utils


class TestRequireAuthenticatedUser(LogTrapTestCase, AsyncTestCase):

    deployer = 'fake-deployer'

    def make_view(self):
        """Return a view to be used for tests.

        The resulting callable must be called with a request object as first
        argument amd with self.deployer as second argument.
        """
        @gen.coroutine
        @utils.require_authenticated_user
        def myview(request, deployer):
            """An example testing view."""
            self.assertEqual(self.deployer, deployer)
            raise utils.response(info='ok')
        return myview

    def make_request(self, is_authenticated=True):
        """Return a mock request, containing a guiserver.auth.User instance.

        If is_authenticated is True, the user in the request is logged in.
        """
        user = auth.User(
            username='user', password='passwd',
            is_authenticated=is_authenticated)
        return mock.Mock(user=user)

    @gen_test
    def test_authenticated(self):
        # The view is executed normally if the user is authenticated.
        view = self.make_view()
        request = self.make_request(is_authenticated=True)
        response = yield view(request, self.deployer)
        self.assertEqual({'Response': 'ok'}, response)

    @gen_test
    def test_not_authenticated(self):
        # The view returns an error response if the user is not authenticated.
        view = self.make_view()
        request = self.make_request(is_authenticated=False)
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
