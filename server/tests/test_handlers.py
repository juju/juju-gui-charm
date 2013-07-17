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

"""Tests for the Juju GUI server handlers."""

from tornado import web
from tornado.testing import AsyncHTTPTestCase

from lib import handlers


class TestHttpsRedirectHandler(AsyncHTTPTestCase):

    def get_app(self):
        return web.Application([(r'.*', handlers.HttpsRedirectHandler)])

    def assert_redirected(self, response, path):
        """Ensure the given response is a permanent redirect to the given path.

        Also check that the URL schema is HTTPS.
        """
        self.assertEqual(301, response.code)
        expected = 'https://localhost:{}{}'.format(self.get_http_port(), path)
        self.assertEqual(expected, response.headers['location'])

    def test_redirection(self):
        # The HTTP traffic is redirected to HTTPS.
        response = self.fetch('/',  follow_redirects=False)
        self.assert_redirected(response, '/')

    def test_page_redirection(self):
        # The path and query parts of the URL are preserved,
        url = '/my/page?my=query'
        response = self.fetch(url, follow_redirects=False)
        self.assert_redirected(response, url)
