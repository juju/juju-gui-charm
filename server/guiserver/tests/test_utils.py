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

"""Tests for the Juju GUI server utilities."""

import json
import unittest

import mock
from tornado import (
    concurrent,
    gen,
    httpclient,
    httpserver,
)
from tornado.testing import (
    AsyncTestCase,
    ExpectLog,
    gen_test,
)

from guiserver import utils


class TestAddFuture(AsyncTestCase):

    def setUp(self):
        # Set up a future object and a result attribute where tests will store
        # their results.
        super(TestAddFuture, self).setUp()
        self.future = concurrent.Future()
        self.result = None

    @gen.coroutine
    def assert_done(self, result):
        """Fire the future and ensure the callback has been called.

        Callbacks in this test case store their results in self.result.
        """
        self.assertTrue(self.future.done())
        self.wait()
        self.assertEqual(result, self.result)

    @gen_test
    def test_without_args(self):
        # A callback without args is correctly called.
        def callback(future):
            self.result = 'future said: ' + future.result()
            self.stop()
        utils.add_future(self.io_loop, self.future, callback)
        self.future.set_result('I am done')
        yield self.assert_done('future said: I am done')

    @gen_test
    def test_with_args(self):
        # A callback with args is correctly called.
        def callback(arg1, arg2, future):
            self.result = [arg1, arg2, future.result()]
            self.stop()
        utils.add_future(self.io_loop, self.future, callback, 1, 2)
        self.future.set_result(3)
        yield self.assert_done([1, 2, 3])


class TestCloneRequest(unittest.TestCase):

    def setUp(self):
        # Set up a server request object.
        self.request = httpserver.HTTPRequest(
            'POST', '/test/', headers={'Content-Type': 'application/json'},
            body='hello')

    def test_request_attributes(self):
        # The resulting request includes the expected attributes.
        request = utils.clone_request(self.request, 'http://example.com/test')
        self.assertEqual('http://example.com/test', request.url)
        self.assertEqual('hello', request.body)
        self.assertEqual({'Content-Type': 'application/json'}, request.headers)
        self.assertEqual('POST', request.method)
        self.assertTrue(request.validate_cert)

    def test_request_body(self):
        # An empty body is set to None.
        original = httpserver.HTTPRequest('GET', '/test/', body='')
        request = utils.clone_request(original, 'http://example.com/test')
        self.assertEqual('http://example.com/test', request.url)
        self.assertIsNone(request.body)

    def test_avoid_validating_certs(self):
        # It is possible to avoid TLS certificates validation.
        request = utils.clone_request(
            self.request, 'http://example.com/test', validate_cert=False)
        self.assertFalse(request.validate_cert)

    def test_request_type(self):
        # The resulting request is a tornado.httpclient.HTTPRequest instance.
        request = utils.clone_request(self.request, 'http://example.com')
        self.assertIsInstance(request, httpclient.HTTPRequest)


class TestGetHeaders(unittest.TestCase):

    def test_propagation(self):
        # The Origin header is propagated if found in the provided request.
        expected = {'Origin': 'https://browser.example.com'}
        request = mock.Mock(headers=expected)
        headers = utils.get_headers(request, 'wss://server.example.com')
        self.assertEqual(expected, headers)

    def test_default(self):
        # If the Origin header is not found, the default is used.
        request = mock.Mock(headers={})
        headers = utils.get_headers(request, 'wss://server.example.com')
        self.assertEqual({'Origin': 'https://server.example.com'}, headers)


class TestGetJujuApiUrl(unittest.TestCase):

    template = '/api/$server/$port/$uuid'
    default = 'wss://example.com:17070/'

    def test_no_match(self):
        # The default URL is returned if there is no match.
        url = utils.get_juju_api_url('/ws', self.template, self.default)
        self.assertEqual(self.default, url)

    def test_precise_match(self):
        # The expected URL is returned when the path matches precisely.
        path = '/api/1.2.3.4/4242/my-uuid'
        url = utils.get_juju_api_url(path, self.template, self.default)
        self.assertEqual('wss://1.2.3.4:4242/environment/my-uuid/api', url)

    def test_prefixed_match(self):
        # The expected URL is returned when the path also includes a prefix.
        path = '/my/prefix/api/1.2.3.4/47/uuid'
        url = utils.get_juju_api_url(path, self.template, self.default)
        self.assertEqual('wss://1.2.3.4:47/environment/uuid/api', url)


class TestJoinUrl(unittest.TestCase):

    def test_url_parts(self):
        # The URL includes the base part, the path and the given query.
        url = utils.join_url(
            'https://example.com:8888/path1', 'path2', 'arg1=value1')
        self.assertEqual(
            'https://example.com:8888/path1/path2?arg1=value1', url)

    def test_no_path(self):
        # The function can be used to just join the base URL and the query.
        url = utils.join_url('https://example.com:8888', '', 'arg1=value1')
        self.assertEqual('https://example.com:8888/?arg1=value1', url)

    def test_no_query(self):
        # The query part can be an empty string.
        url = utils.join_url('https://example.com:8888', 'path2', '')
        self.assertEqual('https://example.com:8888/path2', url)

    def test_strip_slashes(self):
        # Path slashes are properly stripped.
        pairs = [
            ('http://www.example.com', 'path1/path2'),
            ('http://www.example.com/', 'path1/path2'),
            ('http://www.example.com', '/path1/path2'),
            ('http://www.example.com/', '/path1/path2'),
        ]
        expected_url = 'http://www.example.com/path1/path2'
        for base_url, path in pairs:
            url = utils.join_url(base_url, path, '')
            self.assertEqual(
                expected_url, url,
                '{} + {} -> {}'.format(base_url, path, url))


class TestJsonDecodeDict(unittest.TestCase):

    def test_valid(self):
        # A valid JSON is decoded without errors.
        data = {'key1': 'value1', 'key2': 'value2'}
        message = json.dumps(data)
        self.assertEqual(data, utils.json_decode_dict(message))

    def test_invalid_json(self):
        # If the message is not a valid JSON string, a warning is logged and
        # None is returned.
        expected_log = "JSON decoder: message is not valid JSON: 'not-json'"
        with ExpectLog('', expected_log, required=True):
            self.assertIsNone(utils.json_decode_dict('not-json'))

    def test_invalid_type(self):
        # If the resulting object is not a dict-like object, a warning is
        # logged and None is returned.
        expected_log = 'JSON decoder: message is not a dict: \'"not-a-dict"\''
        with ExpectLog('', expected_log, required=True):
            self.assertIsNone(utils.json_decode_dict('"not-a-dict"'))


class TestRequestSummary(unittest.TestCase):

    def test_summary(self):
        # The summary includes the request method, URI and remote IP.
        request = mock.Mock(method='GET', uri='/path', remote_ip='127.0.0.1')
        summary = utils.request_summary(request)
        self.assertEqual('GET /path (127.0.0.1)', summary)


class TestWrapWriteMessage(unittest.TestCase):

    expected_log = "discarding message \(closed connection\): 'hello'"

    def setUp(self):
        self.messages = []
        self.handler = type(
            'Handler', (),
            {'connected': True, 'write_message': self.messages.append}
        )()
        self.wrapped = utils.wrap_write_message(self.handler)

    def test_propagated(self):
        # The JSON encoded version of the message is correctly propagated.
        self.wrapped({'foo': 'bar'})
        self.assertEqual(json.dumps({'foo': 'bar'}), self.messages[0])

    def test_multiple_messages(self):
        # Multiple messages are correctly propagated.
        self.wrapped(1)
        self.wrapped(2)
        self.wrapped(3)
        self.assertEqual(['1', '2', '3'], self.messages)

    def test_connection_closed(self):
        # If the handler connection is closed, a warning is logged and the
        # wrapped method is not called.
        self.handler.connected = False
        with ExpectLog('', self.expected_log, required=True):
            self.wrapped('hello')
        self.assertEqual([], self.messages)

    def test_handler_deleted(self):
        # A warning is logged if the referred handler has been deleted.
        del self.handler
        with ExpectLog('', self.expected_log, required=True):
            self.wrapped('hello')
        self.assertEqual([], self.messages)

    def test_unicode(self):
        # It handles unicode properly.
        snowman = u'{"Here is a snowman\u00a1": "\u2603"}'
        self.wrapped(snowman)
        self.assertEqual(snowman, json.loads(self.messages[0]))


class TestWsToHttp(unittest.TestCase):

    def test_websocket(self):
        # A WebSocket URL is correctly converted.
        url = utils.ws_to_http('ws://example.com')
        self.assertEqual('http://example.com', url)

    def test_secure_websocket(self):
        # A secure WebSocket URL is correctly converted.
        url = utils.ws_to_http('wss://example.com')
        self.assertEqual('https://example.com', url)

    def test_port_and_path(self):
        # The resulting URL includes the WebSocket port and path.
        url = utils.ws_to_http('wss://example.com:42/mypath')
        self.assertEqual('https://example.com:42/mypath', url)
