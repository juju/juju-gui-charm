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

"""Tests for the Juju GUI server clients."""

from tornado import (
    concurrent,
    web,
)
from tornado.testing import (
    AsyncHTTPSTestCase,
    gen_test,
)

from guiserver.tests import helpers


class TestWebSocketClient(AsyncHTTPSTestCase, helpers.WSSTestMixin):

    def setUp(self):
        self.received = []
        self.server_closed_future = concurrent.Future()
        super(TestWebSocketClient, self).setUp()
        # Now that the app is set up, we can create the WebSocket client.
        self.client = helpers.WebSocketClient(
            self.get_wss_url('/'), self.received.append, io_loop=self.io_loop)

    def get_app(self):
        # In this test case, the WebSocket client is connected to a WebSocket
        # echo server, returning each message is received.
        options = {'close_future': self.server_closed_future}
        return web.Application([(r'/', helpers.EchoWebSocketHandler, options)])

    @gen_test
    def test_initial_connection(self):
        # The client correctly establishes a connection to the server.
        yield self.client.connect()
        self.assertTrue(self.client.connected)

    @gen_test
    def test_send_receive(self):
        # The client correctly sends and receives messages on the secure
        # WebSocket connection.
        yield self.client.connect()
        message = yield self.client.write_message('hello')
        self.assertEqual('hello', message)

    @gen_test
    def test_callback(self):
        # The client executes the given callback each time a message is
        # received.
        yield self.client.connect()
        yield self.client.write_message('hello')
        yield self.client.write_message('world')
        self.assertEqual(['hello', 'world'], self.received)

    @gen_test
    def test_queued_messages(self):
        # Messages sent before the connection is established are preserved and
        # sent right after the connection is opened.
        self.client.write_message('hello')
        yield self.client.connect()
        yield self.client.write_message('world')
        yield self.client.close()
        self.assertEqual(['hello', 'world'], self.received)

    @gen_test
    def test_connection_close(self):
        # The client connection can be correctly terminated.
        yield self.client.connect()
        yield self.client.close()
        self.assertFalse(self.client.connected)
        yield self.server_closed_future
