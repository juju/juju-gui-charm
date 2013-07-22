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
    ExpectLog,
    gen_test,
    LogTrapTestCase,
)

from guiserver import (
    clients,
    handlers,
)
from guiserver.tests import helpers


class TestWebSocketHandler(
        AsyncHTTPSTestCase, LogTrapTestCase, helpers.WSSTestMixin):

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
        echo_options = {
            'close_future': self.echo_server_closed_future,
            'io_loop': self.io_loop,
        }
        ws_options = {
            'jujuapi': self.echo_server_address,
            'io_loop': self.io_loop,
        }
        return web.Application([
            (r'/echo', helpers.EchoWebSocketHandler, echo_options),
            (r'/ws', handlers.WebSocketHandler, ws_options),
        ])

    def make_client(self):
        """Return a WebSocket client ready to be connected to the server."""
        url = self.get_wss_url('/ws')
        # The client callback is tested elsewhere.
        callback = lambda message: None
        return clients.websocket_connect(self.io_loop, url, callback)

    def make_handler(self, headers=None):
        """Create and return a WebSocketHandler instance."""
        if headers is None:
            headers = {}
        request = mock.Mock(headers=headers)
        return handlers.WebSocketHandler(self.get_app(), request)

    @gen_test
    def test_initialization(self):
        # A WebSocket client is created and connected when the handler is
        # initialized.
        handler = self.make_handler()
        yield handler.initialize(self.echo_server_address, self.io_loop)
        self.assertTrue(handler.connected)
        self.assertTrue(handler.juju_connected)
        self.assertIsInstance(
            handler.juju_connection, clients.WebSocketClientConnection)
        self.assertEqual(
            self.get_url('/echo'), handler.juju_connection.request.url)

    @gen_test
    def test_juju_connection_failure(self):
        # If the connection to the Juju API server does not succeed, an
        # error is reported and the client is disconnected.
        handler = self.make_handler()
        expected_log = '.*unable to connect to the Juju API'
        with ExpectLog('', expected_log, required=True):
            yield handler.initialize(
                'wss://127.0.0.1/does-not-exist', self.io_loop)
        self.assertFalse(handler.connected)
        self.assertFalse(handler.juju_connected)

    @gen_test
    def test_juju_connection_propagated_request_headers(self):
        # The Origin header is propagated to the client connection.
        handler = self.make_handler(headers={'Origin': 'https://example.com'})
        yield handler.initialize(self.echo_server_address, self.io_loop)
        headers = handler.juju_connection.request.headers
        self.assertIn('Origin', headers)
        self.assertEqual('https://example.com', headers['Origin'])

    @gen_test
    def test_juju_connection_default_request_headers(self):
        # The default Origin header is included in the client connection
        # handshake if not found in the original request.
        handler = self.make_handler()
        yield handler.initialize(self.echo_server_address, self.io_loop)
        headers = handler.juju_connection.request.headers
        self.assertIn('Origin', headers)
        self.assertEqual(self.get_url('/echo'), headers['Origin'])

    @mock.patch('guiserver.handlers.websocket_connect')
    def test_client_callback(self, mock_websocket_connect):
        # The WebSocket client is created passing the proper callback.
        handler = self.make_handler()
        handler.initialize(self.echo_server_address, self.io_loop)
        self.assertEqual(1, mock_websocket_connect.call_count)
        self.assertIn(
            handler.on_juju_message, mock_websocket_connect.call_args[0])

    @mock.patch('guiserver.clients.WebSocketClientConnection')
    def test_from_browser_to_juju(self, mock_juju_connection):
        # A message from the browser is forwarded to the remote server.
        handler = self.make_handler()
        yield handler.initialize(self.echo_server_address, self.io_loop)
        handler.on_message('hello')
        mock_juju_connection.write_message.assert_called_once_with('hello')

    def test_from_juju_to_browser(self):
        # A message from the remote server is returned to the browser.
        handler = self.make_handler()
        handler.initialize(self.echo_server_address, self.io_loop)
        with mock.patch('guiserver.handlers.WebSocketHandler.write_message'):
            handler.on_juju_message('hello')
            handler.write_message.assert_called_once_with('hello')

    @gen_test
    def test_queued_messages(self):
        # Messages sent before the client connection is established are
        # preserved and sent right after the connection is opened.
        handler = self.make_handler()
        mock_path = 'guiserver.clients.WebSocketClientConnection.write_message'
        with mock.patch(mock_path) as mock_write_message:
            initialization = handler.initialize(
                self.echo_server_address, self.io_loop)
            handler.on_message('hello')
            self.assertFalse(mock_write_message.called)
            yield initialization
        mock_write_message.assert_called_once_with('hello')

    @gen_test
    def test_end_to_end_proxy(self):
        # Messages are correctly forwarded from the client to the echo server
        # and back to the client.
        client = yield self.make_client()
        client.write_message('boomerang')
        message = yield client.read_message()
        self.assertEqual('boomerang', message)

    @gen_test
    def test_connection_closed_by_client(self):
        # The proxy connection is terminated when the client disconnects.
        client = yield self.make_client()
        yield client.close()
        yield self.echo_server_closed_future

    @gen_test
    def test_connection_closed_by_server(self):
        # The proxy connection is terminated when the server disconnects.
        client = yield self.make_client()
        # A server disconnection is logged as an error.
        expected_log = '.*Juju API unexpectedly disconnected'
        with ExpectLog('', expected_log, required=True):
            # Fire the future in order to force an echo server disconnection.
            self.echo_server_closed_future.set_result(None)
            message = yield client.read_message()
        self.assertIsNone(message)


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
