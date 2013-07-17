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

from tornado.concurrent import Future
from tornado.testing import (
    AsyncHTTPSTestCase,
    gen_test,
)

from guiserver import clients
from guiserver.tests.utils import echoapp


class TestWebSocketClient(AsyncHTTPSTestCase):

    def setUp(self):
        self.close_future = Future()
        super(TestWebSocketClient, self).setUp()
        self.received = []
        # Now the app is set up, and we can connect the client.
        url = self.get_url('/').replace('https://', 'wss://')
        self.client = clients.WebSocketClient(url, self.received.append)
        self.client.connect()

    def get_app(self):
        return echoapp(self.close_future)

    @gen_test
    def test_send(self):
        self.client.send('hello')

        import pdb; pdb.set_trace()
