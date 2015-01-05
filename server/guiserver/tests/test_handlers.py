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

import datetime
import json
import os
import shutil
import tempfile

from concurrent import futures
import mock
from tornado import (
    concurrent,
    escape,
    gen,
    httpclient,
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
    auth,
    clients,
    get_version,
    handlers,
    manage,
)
from guiserver.bundles import base
from guiserver.tests import helpers


class WebSocketHandlerTestMixin(object):
    """Base set up for all the WebSocketHandler test cases."""

    auth_backend = auth.get_backend(manage.DEFAULT_API_VERSION)
    hello_message = json.dumps({'hello': 'world'})

    def get_app(self):
        # In test cases including this mixin a WebSocket server is created.
        # The server creates a new client on each request. This client should
        # forward messages to a WebSocket echo server. In order to test the
        # communication, some of the tests create another client that connects
        # to the server, e.g.:
        #   ws-client -> ws-server -> ws-forwarding-client -> ws-echo-server
        # Messages arriving to the echo server are returned back to the client:
        #   ws-echo-server -> ws-forwarding-client -> ws-server -> ws-client
        self.apiurl = self.get_wss_url('/echo')
        self.api_close_future = concurrent.Future()
        self.deployer = base.Deployer(
            self.apiurl, manage.DEFAULT_API_VERSION, io_loop=self.io_loop)
        self.tokens = auth.AuthenticationTokenHandler(io_loop=self.io_loop)
        echo_options = {
            'close_future': self.api_close_future,
            'io_loop': self.io_loop,
        }
        ws_options = {
            'apiurl': self.apiurl,
            'auth_backend': self.auth_backend,
            'deployer': self.deployer,
            'io_loop': self.io_loop,
            'tokens': self.tokens,
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

    def make_handler(self, headers=None, mock_protocol=False):
        """Create and return a WebSocketHandler instance."""
        if headers is None:
            headers = {}
        request = mock.Mock(headers=headers)
        handler = handlers.WebSocketHandler(self.get_app(), request)
        if mock_protocol:
            # Mock the underlying connection protocol.
            handler.ws_connection = mock.Mock()
        return handler

    @gen.coroutine
    def make_initialized_handler(
            self, apiurl=None, headers=None, mock_protocol=False):
        """Create and return an initialized WebSocketHandler instance."""
        if apiurl is None:
            apiurl = self.apiurl
        handler = self.make_handler(
            headers=headers, mock_protocol=mock_protocol)
        yield handler.initialize(
            apiurl, self.auth_backend, self.deployer, self.tokens,
            self.io_loop)
        raise gen.Return(handler)


class TestWebSocketHandlerConnection(
        WebSocketHandlerTestMixin, helpers.WSSTestMixin, LogTrapTestCase,
        AsyncHTTPSTestCase):

    def mock_websocket_connect(self):
        """Mock the guiserver.clients.websocket_connect function."""
        future = concurrent.Future()
        future.set_result(mock.Mock())
        mock_websocket_connect = mock.Mock(return_value=future)
        return mock.patch(
            'guiserver.handlers.websocket_connect', mock_websocket_connect)

    @gen_test
    def test_initialization(self):
        # A WebSocket client is created and connected when the handler is
        # initialized.
        handler = yield self.make_initialized_handler()
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
        expected_log = '.*unable to connect to the Juju API'
        with ExpectLog('', expected_log, required=True):
            handler = yield self.make_initialized_handler(
                apiurl='wss://127.0.0.1/no-such')
        self.assertFalse(handler.connected)
        self.assertFalse(handler.juju_connected)

    @gen_test
    def test_juju_connection_propagated_request_headers(self):
        # The Origin header is propagated to the client connection.
        expected = {'Origin': 'https://example.com'}
        handler = yield self.make_initialized_handler(headers=expected)
        headers = handler.juju_connection.request.headers
        self.assertIn('Origin', headers)
        self.assertEqual(expected['Origin'], headers['Origin'])

    @gen_test
    def test_juju_connection_default_request_headers(self):
        # The default Origin header is included in the client connection
        # handshake if not found in the original request.
        handler = yield self.make_initialized_handler()
        headers = handler.juju_connection.request.headers
        self.assertIn('Origin', headers)
        self.assertEqual(self.get_url('/echo'), headers['Origin'])

    @gen_test
    def test_client_callback(self):
        # The WebSocket client is created passing the proper callback.
        with self.mock_websocket_connect() as mock_websocket_connect:
            handler = yield self.make_initialized_handler()
        self.assertEqual(1, mock_websocket_connect.call_count)
        self.assertIn(
            handler.on_juju_message, mock_websocket_connect.call_args[0])

    @gen_test
    def test_connection_closed_by_client(self):
        # The proxy connection is terminated when the client disconnects.
        client = yield self.make_client()
        client.close()
        yield self.api_close_future

    @gen_test
    def test_connection_closed_by_server(self):
        # The proxy connection is terminated when the server disconnects.
        client = yield self.make_client()
        # A server disconnection is logged as an error.
        expected_log = '.*Juju API unexpectedly disconnected'
        with ExpectLog('', expected_log, required=True):
            # Fire the Future in order to force an echo server disconnection.
            self.api_close_future.set_result(None)
            message = yield client.read_message()
        self.assertIsNone(message)

    def test_select_subprotocol(self):
        # The first sub-protocol is returned by the handler method.
        handler = self.make_handler()
        subprotocol = handler.select_subprotocol(['foo', 'bar'])
        self.assertEqual('foo', subprotocol)


class TestWebSocketHandlerProxy(
        WebSocketHandlerTestMixin, helpers.WSSTestMixin, LogTrapTestCase,
        AsyncHTTPSTestCase):

    @mock.patch('guiserver.clients.WebSocketClientConnection')
    def test_from_browser_to_juju(self, mock_juju_connection):
        # A message from the browser is forwarded to the remote server.
        handler = yield self.make_initialized_handler()
        handler.on_message(self.hello_message)
        mock_juju_connection.write_message.assert_called_once_with(
            self.hello_message)

    @gen_test
    def test_from_juju_to_browser(self):
        # A message from the remote server is returned to the browser.
        handler = yield self.make_initialized_handler()
        with mock.patch('guiserver.handlers.WebSocketHandler.write_message'):
            handler.on_juju_message(self.hello_message)
            handler.write_message.assert_called_once_with(self.hello_message)

    @gen_test
    def test_queued_messages(self):
        # Messages sent before the client connection is established are
        # preserved and sent right after the connection is opened.
        handler = self.make_handler()
        mock_path = 'guiserver.clients.WebSocketClientConnection.write_message'
        with mock.patch(mock_path) as mock_write_message:
            initialization = handler.initialize(
                self.apiurl, self.auth_backend, self.deployer, self.tokens,
                io_loop=self.io_loop)
            handler.on_message(self.hello_message)
            self.assertFalse(mock_write_message.called)
            yield initialization
        mock_write_message.assert_called_once_with(self.hello_message)

    @gen_test
    def test_end_to_end_proxy(self):
        # Messages are correctly forwarded from the client to the echo server
        # and back to the client.
        client = yield self.make_client()
        client.write_message(self.hello_message)
        message = yield client.read_message()
        self.assertEqual(self.hello_message, message)

    @gen_test
    def test_end_to_end_proxy_non_ascii(self):
        # Non-ascii messages are correctly forwarded from the client to the
        # echo server and back to the client.
        snowman = u'{"Here is a snowman\u00a1": "\u2603"}'
        client = yield self.make_client()
        client.write_message(snowman)
        message = yield client.read_message()
        self.assertEqual(snowman, message)

    @gen_test
    def test_invalid_json(self):
        # A warning is logged if the message is not valid JSON.
        client = yield self.make_client()
        expected_log = "JSON decoder: message is not valid JSON: u'not-json'"
        with ExpectLog('', expected_log, required=True):
            client.write_message('not-json')
            yield client.read_message()

    @gen_test
    def test_not_a_dict(self):
        # A warning is logged if the decoded message is not a dict.
        client = yield self.make_client()
        expected_log = 'JSON decoder: message is not a dict: u\'"not-a-dict"\''
        with ExpectLog('', expected_log, required=True):
            client.write_message('"not-a-dict"')
            yield client.read_message()


class TestWebSocketHandlerAuthentication(
        WebSocketHandlerTestMixin, helpers.WSSTestMixin,
        helpers.GoAPITestMixin, LogTrapTestCase, AsyncHTTPSTestCase):

    def setUp(self):
        super(TestWebSocketHandlerAuthentication, self).setUp()
        self.handler = self.make_handler(mock_protocol=True)
        self.handler.initialize(
            self.apiurl, self.auth_backend, self.deployer, self.tokens,
            io_loop=self.io_loop)

    def send_login_request(self):
        """Create a login request and send it to the handler."""
        request = self.make_login_request(encoded=True)
        self.handler.on_message(request)

    def send_login_response(self, successful):
        """Create a login response and send it to the handler."""
        response = self.make_login_response(
            successful=successful, encoded=True)
        self.handler.on_juju_message(response)

    def test_authentication_success(self):
        # The authentication process completes and the user is logged in.
        self.assertFalse(self.handler.user.is_authenticated)
        self.send_login_request()
        self.assertFalse(self.handler.user.is_authenticated)
        self.assertTrue(self.handler.auth.in_progress())
        self.send_login_response(True)
        self.assertTrue(self.handler.user.is_authenticated)
        self.assertFalse(self.handler.auth.in_progress())

    def test_authentication_failure(self):
        # The user is not logged in if the authentication fails.
        self.send_login_request()
        self.send_login_response(False)
        self.assertFalse(self.handler.user.is_authenticated)
        self.assertFalse(self.handler.auth.in_progress())

    def test_already_logged_in(self):
        # Authentication is no longer attempted if the user already logged in.
        self.send_login_request()
        self.send_login_response(True)
        self.send_login_request()
        self.assertTrue(self.handler.user.is_authenticated)
        self.assertFalse(self.handler.auth.in_progress())

    def test_not_in_progress(self):
        # Authentication responses are not processed if the authentication is
        # not in progress.
        self.send_login_response(True)
        self.assertFalse(self.handler.user.is_authenticated)
        self.assertFalse(self.handler.auth.in_progress())

    @mock.patch('uuid.uuid4', mock.Mock(return_value=mock.Mock(hex='DEFACED')))
    @mock.patch('datetime.datetime',
                mock.Mock(
                    **{'utcnow.return_value':
                       datetime.datetime(2013, 11, 21, 21)}))
    def test_token_request(self):
        # It supports requesting a token when authenticated.
        self.handler.user.username = 'user'
        self.handler.user.password = 'passwd'
        self.handler.user.is_authenticated = True
        request = json.dumps(
            dict(RequestId=42, Type='GUIToken', Request='Create'))
        self.handler.on_message(request)
        message = self.handler.ws_connection.write_message.call_args[0][0]
        self.assertEqual(
            dict(
                RequestId=42,
                Response=dict(
                    Token='DEFACED',
                    Created='2013-11-21T21:00:00Z',
                    Expires='2013-11-21T21:02:00Z'
                )
            ),
            json.loads(message))
        self.assertFalse(self.handler.juju_connected)
        self.assertEqual(0, len(self.handler._juju_message_queue))

    def test_unauthenticated_token_request(self):
        # When not authenticated, the request is passed on to Juju for error.
        self.assertFalse(self.handler.user.is_authenticated)
        request = json.dumps(
            dict(RequestId=42, Type='GUIToken', Request='Create'))
        self.handler.on_message(request)
        message = self.handler.ws_connection.write_message.call_args[0][0]
        self.assertEqual(
            dict(
                RequestId=42,
                Error='tokens can only be created by authenticated users.',
                ErrorCode='unauthorized access',
                Response={},
            ),
            json.loads(message))
        self.assertFalse(self.handler.juju_connected)
        self.assertEqual(0, len(self.handler._juju_message_queue))

    def test_token_authentication_success(self):
        # It supports authenticating with a token.
        request = self.make_token_login_request(
            self.tokens, username='user', password='passwd')
        with mock.patch.object(self.io_loop,
                               'remove_timeout') as mock_remove_timeout:
            self.handler.on_message(json.dumps(request))
            mock_remove_timeout.assert_called_once_with('handle')
        self.assertEqual(
            self.make_login_request(
                request_id=42, username='user', password='passwd'),
            json.loads(self.handler._juju_message_queue[0]))
        self.assertTrue(self.handler.auth.in_progress())
        self.send_login_response(True)
        self.assertEqual(
            dict(RequestId=42,
                 Response={'AuthTag': 'user', 'Password': 'passwd'}),
            json.loads(
                self.handler.ws_connection.write_message.call_args[0][0]))

    def test_token_authentication_failure(self):
        # It correctly handles a token that will not authenticate.
        request = self.make_token_login_request(
            self.tokens, username='user', password='passwd')
        with mock.patch.object(self.io_loop,
                               'remove_timeout') as mock_remove_timeout:
            self.handler.on_message(json.dumps(request))
            mock_remove_timeout.assert_called_once_with('handle')
        self.send_login_response(False)
        message = self.handler.ws_connection.write_message.call_args[0][0]
        self.assertEqual(
            'invalid entity name or password',
            json.loads(message)['Error'])

    def test_unknown_authentication_token(self):
        # It correctly handles an unknown token.
        request = self.make_token_login_request()
        self.handler.on_message(json.dumps(request))
        message = self.handler.ws_connection.write_message.call_args[0][0]
        self.assertEqual(
            'unknown, fulfilled, or expired token',
            json.loads(message)['Error'])
        self.assertFalse(self.handler.juju_connected)
        self.assertEqual(0, len(self.handler._juju_message_queue))


class TestWebSocketHandlerBundles(
        WebSocketHandlerTestMixin, helpers.WSSTestMixin,
        helpers.BundlesTestMixin, LogTrapTestCase, AsyncHTTPSTestCase):

    @gen_test
    def test_bundle_import_process(self):
        # The bundle import process is correctly started and completed.
        write_message_path = 'guiserver.handlers.wrap_write_message'
        with mock.patch(write_message_path) as mock_write_message:
            handler = yield self.make_initialized_handler()
        # Simulate the user is authenticated.
        handler.user.is_authenticated = True
        # Start a bundle import.
        request = self.make_deployment_request('Import', encoded=True)
        with self.patch_validate(), self.patch_import_bundle():
            yield handler.on_message(request)
        expected = self.make_deployment_response(response={'DeploymentId': 0})
        mock_write_message().assert_called_once_with(expected)
        # Start observing the deployment progress.
        request = self.make_deployment_request('Watch', encoded=True)
        yield handler.on_message(request)
        expected = self.make_deployment_response(response={'WatcherId': 0})
        mock_write_message().assert_called_with(expected)
        # Get the two next changes: in the first one the deployment has been
        # started, in the second one it is completed. This way the test runner
        # can safely stop the IO loop (no remaining Future callbacks).
        request = self.make_deployment_request('Next', encoded=True)
        yield handler.on_message(request)
        yield handler.on_message(request)

    @gen_test
    def test_not_authenticated(self):
        # The bundle deployment support is only activated for logged in users.
        client = yield self.make_client()
        request = self.make_deployment_request('Import', encoded=True)
        client.write_message(request)
        expected = self.make_deployment_response(
            error='unauthorized access: no user logged in')
        response = yield client.read_message()
        self.assertEqual(expected, json.loads(response))


class TestIndexHandler(LogTrapTestCase, AsyncHTTPTestCase):

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

    def test_headers(self):
        # The expected Content-Type, ETag and clickjacking protection headers
        # are correctly sent by the server.
        response = self.fetch('/')
        headers = response.headers
        # Check response content type.
        self.assertIn('Content-Type', headers)
        self.assertEqual('text/html', headers['Content-Type'])
        # Check cache headers.
        self.assertIn('ETag', headers)
        self.assertIn('Last-Modified', headers)
        # Check X-Frame headers.
        self.assertIn('X-Frame-Options', headers)
        self.assertEqual('SAMEORIGIN', headers['X-Frame-Options'])


class TestProxyHandler(LogTrapTestCase, AsyncHTTPTestCase):

    target_url = 'https://api.example.com:17070'
    request_headers = {
        'Accept-Encoding': 'gzip',
        'Authorization': 'Basic auth',
    }
    response_headers = {
        'Cache-Control': 'no-cache',
        'Content-Type': 'text/html',
        'Date': 'Tue, 15 Nov 1994 08:12:31 GMT',
        'Location': 'http://example.com/location',
        'Server': 'Apache/2.4.1 (Unix)',
        'WWW-Authenticate': 'Basic',
    }
    expected_validate_cert = True

    def get_app(self):
        # Set up an application exposing the proxy handler.
        options = {'target_url': self.target_url}
        return web.Application([
            (r'^/base/(.*)', handlers.ProxyHandler, options)])

    def assert_include_headers(self, expected, headers):
        """Ensure the expected headers are included in the given ones."""
        for key, value in expected.items():
            self.assertIn(key, headers)
            self.assertEqual(value, headers[key])

    def patch_http_client(self, response):
        """Patch the asynchronous HTTP client used to fetch remote resources.

        The patched client returns a future whose result is the given response
        object. If the response is an HTTPError exception, the future will
        raise the given exception.
        """
        future = futures.Future()
        if isinstance(response, httpclient.HTTPError):
            future.set_exception(response)
        else:
            future.set_result(response)
        mock_client = mock.Mock()
        mock_client().fetch.return_value = future
        mock_client.reset_mock()
        return mock.patch('tornado.httpclient.AsyncHTTPClient', mock_client)

    def test_get_request(self):
        # GET requests are properly sent to the target URL. Responses are
        # propagated back to the client.
        remote_response = helpers.make_response(
            200, body='ok', headers=self.response_headers)
        with self.patch_http_client(remote_response) as mock_client:
            response = self.fetch(
                '/base/remote-path/', headers=self.request_headers)
        # The remote response is propagated to the original client.
        self.assertEqual(200, response.code)
        self.assertEqual('ok', response.body)
        self.assert_include_headers(self.response_headers, response.headers)
        # An asynchronous HTTP client has been correctly created.
        mock_client.assert_called_once_with()
        # The client's fetch method has been used to fetch the remote resource.
        mock_fetch = mock_client().fetch
        self.assertEqual(1, mock_fetch.call_count)
        # The request to the target URL is a clone of the original request.
        remote_request = mock_fetch.call_args[0][0]
        self.assertEqual('GET', remote_request.method)
        self.assertEqual(self.target_url + '/remote-path/', remote_request.url)
        self.assert_include_headers(
            self.request_headers, remote_request.headers)

    def test_post_request(self):
        # POST requests are properly sent to the target URL.
        remote_response = helpers.make_response(
            200, body='ok', headers=self.response_headers)
        with self.patch_http_client(remote_response) as mock_client:
            response = self.fetch(
                '/base/remote-path/', method='POST',
                headers=self.request_headers, body='original body')
        self.assertEqual(200, response.code)
        self.assertEqual('ok', response.body)
        self.assert_include_headers(self.response_headers, response.headers)
        # The client's fetch method has been used to fetch the remote resource.
        mock_fetch = mock_client().fetch
        self.assertEqual(1, mock_fetch.call_count)
        # The request to the target URL is a clone of the original request.
        remote_request = mock_fetch.call_args[0][0]
        self.assertEqual('POST', remote_request.method)
        self.assert_include_headers(
            self.request_headers, remote_request.headers)
        # Also the body is propagated.
        self.assertEqual('original body', remote_request.body)

    def test_validate_certificates(self):
        # Server certificates are properly handled.
        remote_response = helpers.make_response(200)
        with self.patch_http_client(remote_response) as mock_client:
            self.fetch('/base/remote-path/', headers=self.request_headers)
        mock_fetch = mock_client().fetch
        # The client's fetch method has been used to fetch the remote resource.
        mock_fetch = mock_client().fetch
        self.assertEqual(1, mock_fetch.call_count)
        remote_request = mock_fetch.call_args[0][0]
        self.assertEqual(
            self.expected_validate_cert, remote_request.validate_cert)

    def test_remote_path(self):
        # The corresponding path on the remote server is properly generated.
        remote_response = helpers.make_response(200)
        with self.patch_http_client(remote_response) as mock_client:
            self.fetch('/base/path1/path2?arg1=valu1&arg2=value2')
        mock_fetch = mock_client().fetch
        remote_request = mock_fetch.call_args[0][0]
        # The remote path reflects the requested one: the /base/ namespace is
        # correctly removed.
        self.assertEqual(
            self.target_url + '/path1/path2?arg1=valu1&arg2=value2',
            remote_request.url)

    def test_error_response(self):
        # Error responses are returned to the original client.
        remote_response = helpers.make_response(400, body='try harder')
        with self.patch_http_client(remote_response):
            response = self.fetch('/base/remote-path/')
        self.assertEqual(400, response.code)
        self.assertEqual('try harder', response.body)
        self.assertEqual('Bad Request', response.reason)

    def test_not_found_response(self):
        # 404 responses are returned to the original client.
        remote_response = helpers.make_response(404, body='try later')
        with self.patch_http_client(remote_response):
            response = self.fetch('/base/remote-path/')
        self.assertEqual(404, response.code)
        self.assertEqual('try later', response.body)
        self.assertEqual('Not Found', response.reason)

    def test_internal_server_error(self):
        # A 500 error is returned if an HTTP error occurs during the remote
        # request/response process.
        error = httpclient.HTTPError(500, message='bad wolf')
        with self.patch_http_client(error):
            response = self.fetch('/base/remote-path/')
        self.assertEqual(500, response.code)
        self.assertEqual(
            'Internal server error:\n'
            'error fetching data from '
            'https://api.example.com:17070/remote-path/: '
            'HTTP 500: bad wolf', response.body)
        self.assertEqual('Internal Server Error', response.reason)


class TestJujuProxyHandler(TestProxyHandler):

    charmworld_url = 'https://charmworld.example.com'
    expected_validate_cert = False

    def get_app(self):
        # Set up an application exposing the proxy handler.
        options = {
            'target_url': self.target_url,
            'charmworld_url': self.charmworld_url,
        }
        return web.Application([
            (r'^/base/(.*)', handlers.JujuProxyHandler, options)])

    def test_default_charm_icon(self):
        # If a charm icon is not found, a GET request redirects to the fallback
        # icon available on charmworld.
        remote_response = helpers.make_response(404)
        path = '/base/charms?url=local:trusty/django=42&file=icon.svg'
        with self.patch_http_client(remote_response):
            response = self.fetch(path, follow_redirects=False)
        self.assertEqual(302, response.code)
        self.assertEqual(
            self.charmworld_url + handlers.DEFAULT_CHARM_ICON_PATH,
            response.headers['location'])

    def test_charm_file_not_found(self):
        # If a charm file is not found and it is not the icon, a 404 is
        # correctly returned to the original client.
        remote_response = helpers.make_response(404)
        path = '/base/charms?url=local:trusty/django=42&file=readme.rst'
        with self.patch_http_client(remote_response):
            response = self.fetch(path)
        self.assertEqual(404, response.code)
        self.assertEqual('Not Found', response.reason)


class TestInfoHandler(LogTrapTestCase, AsyncHTTPTestCase):

    def get_app(self):
        mock_deployer = mock.Mock()
        mock_deployer.status.return_value = 'deployments status'
        options = {
            'apiurl': 'wss://api.example.com:17070',
            'apiversion': 'clojure',
            'deployer': mock_deployer,
            'sandbox': False,
            'start_time': 10,
        }
        return web.Application([(r'^/info', handlers.InfoHandler, options)])

    @mock.patch('time.time', mock.Mock(return_value=52))
    def test_info(self):
        # The handler correctly returns information about the GUI server.
        expected = {
            'apiurl': 'wss://api.example.com:17070',
            'apiversion': 'clojure',
            'debug': False,
            'deployer': 'deployments status',
            'sandbox': False,
            'uptime': 42,
            'version': get_version(),
        }
        response = self.fetch('/info')
        self.assertEqual(200, response.code)
        self.assertEqual(
            'application/json; charset=UTF-8',
            response.headers['Content-Type'])
        info = escape.json_decode(response.body)
        self.assertEqual(expected, info)


class TestHttpsRedirectHandler(LogTrapTestCase, AsyncHTTPTestCase):

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
