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

"""Juju GUI server test utilities."""

from tornado import websocket


class EchoWebSocketHandler(websocket.WebSocketHandler):
    """A WebSocket server echoing back messages."""

    def initialize(self, close_future, io_loop):
        """Echo WebSocket server initializer.

        The handler receives a close Future and the current Tornado IO loop.
        The close Future is fired when the connection is closed.
        The close Future can also be used to force a connection termination by
        manually firing it.
        """
        self._closed_future = close_future
        self._connected = True
        io_loop.add_future(close_future, self.force_close)

    def force_close(self, future):
        """Close the connection to the client."""
        if self._connected:
            self.close()

    def on_message(self, message):
        """Echo back the received message."""
        self.write_message(message, isinstance(message, bytes))

    def on_close(self):
        """Fire the _closed_future if not already done."""
        self._connected = False
        if not self._closed_future.done():
            self._closed_future.set_result(None)


class WSSTestMixin(object):
    """Add some helper methods for testing secure WebSocket handlers."""

    def get_wss_url(self, path):
        """Return an absolute secure WebSocket url for the given path."""
        return 'wss://localhost:{}{}'.format(self.get_http_port(), path)
