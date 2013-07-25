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
from tornado.testing import ExpectLog

from guiserver import utils


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


class TestJsonDecodeDict(unittest.TestCase):

    def test_valid(self):
        # A valid JSON is decoded without errors.
        data = {'key1': 'value1', 'key2': 'value2'}
        message = json.dumps(data)
        self.assertEqual(data, utils.json_decode_dict(message))

    def test_invalid_json(self):
        # If the message is not a valid JSON string, a warning is logged and
        # None is returned.
        expected_log = 'JSON decoder: message is not valid JSON: not-json'
        with ExpectLog('', expected_log, required=True):
            self.assertIsNone(utils.json_decode_dict('not-json'))

    def test_invalid_type(self):
        # If the resulting object is not a dict-like object, a warning is
        # logged and None is returned.
        expected_log = 'JSON decoder: message is not a dict: "not-a-dict"'
        with ExpectLog('', expected_log, required=True):
            self.assertIsNone(utils.json_decode_dict('"not-a-dict"'))


class TestRequestSummary(unittest.TestCase):

    def test_summary(self):
        # The summary includes the request method, URI and remote IP.
        request = mock.Mock(method='GET', uri='/path', remote_ip='127.0.0.1')
        summary = utils.request_summary(request)
        self.assertEqual('GET /path (127.0.0.1)', summary)


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
