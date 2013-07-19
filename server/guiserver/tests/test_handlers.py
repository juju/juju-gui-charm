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

import mock
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

from guiserver import (
    clients,
    handlers,
)
from guiserver.tests import helpers


class TestWebSocketHandler(AsyncHTTPSTestCase, helpers.WSSTestMixin):

    def get_app(self):
        # In this test case a WebSocket server is created. The server creates a
        # new client on each request. This client should forward messages to a
        # WebSocket echo server. In order to test the communication, some of
        # the tests create another client that connects to the server, e.g.:
        #   ws-client -> ws-server -> ws-forwarding-client -> ws-echo-server
        # Messages arriving to the echo server are returned back to the client:
        #   ws-echo-server -> ws-forwarding-client -> ws-server -> ws-client
        self.echo_server_address = self.get_wss_url('/echo')
        self.echo_server_closed_future = concurrent.Future()
        echo_options = {'close_future': self.echo_server_closed_future}
        ws_options = {'jujuapi': self.echo_server_address}
        return web.Application([
            (r'/echo', helpers.EchoWebSocketHandler, echo_options),
            (r'/ws', handlers.WebSocketHandler, ws_options),
        ])

    def make_client(self):
        """Return a WebSocket client ready to be connected to the server."""
        url = self.get_wss_url('/ws')
        # The client callback is tested elsewhere.
        callback = lambda message: None
        return helpers.WebSocketClient(url, callback, io_loop=self.io_loop)

    def make_handler(self):
        """Create and return a WebSocketHandler instance."""
        request = mock.Mock()
        return handlers.WebSocketHandler(self.get_app(), request)

    @gen_test
    def test_initialization(self):
        # A WebSocket client is created and connected when the handler is
        # initialized.
        handler = self.make_handler()
        yield handler.initialize(self.echo_server_address)
        self.assertIsInstance(handler.jujuconn, clients.WebSocketClient)
        self.assertTrue(handler.jujuconn.connected)

    def test_client_callback(self):
        # The WebSocket client is created passing the proper callback.
        handler = self.make_handler()
        with mock.patch('guiserver.handlers.WebSocketClient') as mock_client:
            handler.initialize(self.echo_server_address)
            mock_client.assert_called_once_with(
                self.echo_server_address, handler.on_juju_message)

    def test_from_browser_to_juju(self):
        # A message from the browser is forwarded to the remote server.
        handler = self.make_handler()
        with mock.patch('guiserver.handlers.WebSocketClient'):
            handler.initialize(self.echo_server_address)
        handler.on_message('hello')
        handler.jujuconn.write_message.assert_called_once_with('hello')

    def test_from_juju_to_browser(self):
        # A message from the remote server is returned to the browser.
        handler = self.make_handler()
        handler.initialize(self.echo_server_address)
        with mock.patch('guiserver.handlers.WebSocketHandler.write_message'):
            handler.on_juju_message('hello')
            handler.write_message.assert_called_once_with('hello')

    @gen_test
    def test_end_to_end_proxy(self):
        # Messages are correctly forwarded from the client to the echo server
        # and back to the client.
        client = self.make_client()
        yield client.connect()
        message = yield client.send('hello')
        self.assertEqual('hello', message)

    @gen_test
    def test_connection_close(self):
        # The proxy connection is terminated when the client disconnects.
        client = self.make_client()
        yield client.connect()
        yield client.close()
        self.assertFalse(client.connected)
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
