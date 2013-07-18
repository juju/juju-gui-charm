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

import logging
import os

from tornado import (
    gen,
    web,
    websocket,
)

from guiserver.clients import WebSocketClient


class WebSocketHandler(websocket.WebSocketHandler):
    """WebSocket handler supporting secure WebSockets.

    This handler acts as a proxy between the browser connection and the
    Juju API server.
    """

    @gen.coroutine
    def initialize(self, jujuapi):
        """Create a new WebSocket client and connect it to the Juju API."""
        logging.debug('ws server: connecting to juju')
        self.jujuconn = WebSocketClient(jujuapi, self.on_juju_message)
        yield self.jujuconn.connect()
        logging.debug('ws server: connected to juju')

    def on_message(self, message):
        """Hook called when a new message is received from the browser.

        The message is propagated to the Juju API server.
        """
        logging.debug('ws server: browser --> juju: {}'.format(message))
        self.jujuconn.write_message(message)

    def on_juju_message(self, message):
        """Hook called when a new message is received from the Juju API server.

        The message is propagated to the browser.
        """
        logging.debug('ws server: juju --> browser: {}'.format(message))
        self.write_message(message)

    @gen.coroutine
    def on_close(self):
        """Hook called when the WebSocket connection is terminated."""
        logging.debug('ws server: connection closed')
        yield self.jujuconn.close()
        self.jujuconn = None


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
