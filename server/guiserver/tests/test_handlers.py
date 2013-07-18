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

import os
import shutil
import tempfile

from tornado import (
    concurrent,
    web,
)
from tornado.testing import (
    AsyncHTTPTestCase,
    AsyncHTTPSTestCase,
    gen_test,
    LogTrapTestCase,
)

from guiserver import handlers
from guiserver.tests import helpers


class TestWebSocketHandler(AsyncHTTPSTestCase, helpers.WSSTestMixin):

    def setUp(self):
        self.echo_server_closed_future = concurrent.Future()
        super(TestWebSocketHandler, self).setUp()
        # Now that the app is set up, we can create the WebSocket client.
        self.client = helpers.WebSocketClient(
            self.get_wss_url('/ws'),
            lambda message: None,
            io_loop=self.io_loop)

    def get_app(self):
        # In this test case, the WebSocket server creates a new client on each
        # request. This client should forward messages to a WebSocket echo
        # server. In order to test the communication, another client is created
        # and connected to the server, e.g.:
        #   ws-client -> ws-server -> ws-forwarding-client -> ws-echo-server
        # Messages arriving to the echo server are returned back to the client:
        #   ws-echo-server -> ws-forwarding-client -> ws-server -> ws-client
        echo_options = {'close_future': self.echo_server_closed_future}
        ws_options = {'jujuapi': self.get_wss_url('/echo')}
        return web.Application([
            (r'/echo', helpers.EchoWebSocketHandler, echo_options),
            (r'/ws', handlers.WebSocketHandler, ws_options),
        ])

    @gen_test
    def test_proxy(self):
        # Messages are correctly forwarded from the client to the echo server
        # and back to the client.
        yield self.client.connect()
        message = yield self.client.send('hello')
        self.assertEqual('hello', message)

    @gen_test
    def test_connection_close(self):
        # The proxy connection is terminated when the client disconnects.
        yield self.client.connect()
        yield self.client.close()
        self.assertFalse(self.client.connected)
        yield self.echo_server_closed_future


class TestIndexHandler(AsyncHTTPTestCase, LogTrapTestCase):

    def setUp(self):
        # Set up a static path with an index.html in it.
        self.path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.path)
        self.index_contents = 'We are the Borg!'
        index_path = os.path.join(self.path, 'index.html')
        with open(index_path, 'w') as index_file:
            index_file.write(self.index_contents)
        super(TestIndexHandler, self).setUp()

    def get_app(self):
        return web.Application([
            (r'/(.*)', handlers.IndexHandler, {'path': self.path}),
        ])

    def ensure_index(self, path):
        """Ensure the index contents are returned requesting the given path."""
        response = self.fetch(path)
        self.assertEqual(200, response.code)
        self.assertEqual(self.index_contents, response.body)

    def test_root(self):
        # Requests for the root path are served by the index file.
        self.ensure_index('/')

    def test_page(self):
        # Requests for internal pages are served by the index file.
        self.ensure_index('/resistance/is/futile')

    def test_page_with_flags_and_queries(self):
        # Requests including flags and queries are served by the index file.
        self.ensure_index('/:flag:/activated/?my=query')


class TestHttpsRedirectHandler(AsyncHTTPTestCase, LogTrapTestCase):

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
        response = self.fetch('/', follow_redirects=False)
        self.assert_redirected(response, '/')

    def test_page_redirection(self):
        # The path and query parts of the URL are preserved,
        path_and_query = '/my/page?my=query'
        response = self.fetch(path_and_query, follow_redirects=False)
        self.assert_redirected(response, path_and_query)
