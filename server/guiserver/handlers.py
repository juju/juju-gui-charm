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

"""Juju GUI server HTTP/HTTPS handlers."""

from collections import deque
import logging
import os

from tornado import (
    gen,
    web,
    websocket,
)
from tornado.ioloop import IOLoop

from guiserver.clients import websocket_connect
from guiserver.utils import (
    get_headers,
    request_summary,
)


class WebSocketHandler(websocket.WebSocketHandler):
    """WebSocket handler supporting secure WebSockets.

    This handler acts as a proxy between the browser connection and the
    Juju API server.

    Relevant attributes:

      - connected: True if the current browser is connected, False otherwise;
      - juju_connected: True if the Juju API is connected, False otherwise;
      - juju_connection: the WebSocket client connection to the Juju API;

    Callbacks:

      - on_message(message): called when a message arrives from the browser;
      - on_juju_message(message): called when a message arrives from Juju;
      - on_close(): called when the browser closes the connection;
      - on_juju_close(): called when juju closes the connection;

    Methods:
      - write_message(message): send a message to the browser;
      - close(): terminate the browser connection.

    """

    @gen.coroutine
    def initialize(self, jujuapi, io_loop=None):
        """Create a new WebSocket client and connect it to the Juju API."""
        self._summary = request_summary(self.request) + ' '
        logging.info(self._summary + 'client connected')
        self._io_loop = io_loop or IOLoop.current()
        self.connected = True
        self.juju_connected = False
        self._juju_message_queue = queue = deque()
        # Juju requires the Origin header to be included in the WebSocket
        # client handshake request. Propagate the client origin if present;
        # use the Juju API server as origin otherwise.
        headers = get_headers(self.request, jujuapi)
        self._juju_connected_future = websocket_connect(
            self._io_loop, jujuapi, self.on_juju_message, headers=headers)
        try:
            self.juju_connection = yield self._juju_connected_future
        except Exception as err:
            logging.error(self._summary + 'unable to connect to the Juju API')
            logging.exception(err)
            self.connected = False
            raise gen.Return()
        self.juju_connected = True
        logging.info(self._summary + 'Juju API connected')
        # Send all the messages that have been enqueued before the connection
        # to the Juju API server was established.
        while self.connected and self.juju_connected and len(queue):
            message = queue.popleft()
            logging.debug(self._summary + 'queue -> juju: {}'.format(message))
            self.juju_connection.write_message(message)

    def on_message(self, message):
        """Hook called when a new message is received from the browser.

        The message is propagated to the Juju API server.
        Messages sent before the client connection to the Juju API server is
        established are queued for later delivery.
        """
        if self.juju_connected:
            logging.debug(self._summary + 'client -> juju: {}'.format(message))
            return self.juju_connection.write_message(message)
        logging.debug(self._summary + 'client -> queue: {}'.format(message))
        self._juju_message_queue.append(message)

    def on_juju_message(self, message):
        """Hook called when a new message is received from the Juju API server.

        The message is propagated to the browser.
        """
        if message is None:
            return self.on_juju_close()
        else:
            logging.debug(self._summary + 'juju -> client: {}'.format(message))
            self.write_message(message)

    def on_close(self):
        """Hook called when the WebSocket connection is terminated."""
        logging.info(self._summary + 'client connection closed')
        self.connected = False
        # At this point the WebSocket client connection to the Juju API server
        # could be not yet established. For this reason the connection is
        # terminated adding a callback to the corresponding future.
        callback = lambda _: self.juju_connection.close()
        self._io_loop.add_future(self._juju_connected_future, callback)

    def on_juju_close(self):
        """Hook called when the WebSocket connection to Juju is terminated."""
        logging.info(self._summary + 'Juju API connection closed')
        self.juju_connected = False
        self.juju_connection = None
        # Usually the Juju API connection is terminated as a consequence of a
        # browser disconnection. A server disconnection is unexpected and
        # unlikely to happen. In the future Juju will support HA and we will
        # need to react accordingly to server disconnections, but for the time
        # being we just disconnect the browser and log an error.
        if self.connected:
            logging.error(self._summary + 'Juju API unexpectedly disconnected')
            self.close()


class IndexHandler(web.StaticFileHandler):
    """Serve all requests using the index.html file placed in the static root.
    """

    @classmethod
    def get_absolute_path(cls, root, path):
        """See tornado.web.StaticFileHandler.get_absolute_path."""
        return os.path.join(root, 'index.html')


class HttpsRedirectHandler(web.RequestHandler):
    """Permanently redirect all the requests to the equivalent HTTPS URL."""

    def get(self):
        """Handle GET requests."""
        request = self.request
        url = 'https://{}{}'.format(request.host, request.uri)
        self.redirect(url, permanent=True)
