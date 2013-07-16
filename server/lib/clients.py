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

"""Juju GUI server websocket clients."""

from collections import deque
import logging

from ws4py.client import tornadoclient


class WebSocketClient(tornadoclient.TornadoWebSocketClient):

    def __init__(self, url, on_message_received, *args, **kwargs):
        super(WebSocketClient, self).__init__(url, *args, **kwargs)
        self.connected = False
        self._queue = deque()
        self._on_message_received = on_message_received

    def opened(self):
        logging.debug('ws client: connected')
        self.connected = True
        queue = self._queue
        while self.connected and len(queue):
            self.send(queue.popleft())

    def received_message(self, message):
        logging.debug('ws client: received message: {}'.format(message))
        # FIXME: why message.data and not just message?
        self._on_message_received(message.data)

    def send(self, message, *args, **kwargs):
        logging.debug('ws client: send message: {}'.format(message))
        # FIXME: why do we have to redefine self.sock here?
        self.sock = self.io.socket
        super(WebSocketClient, self).send(message, *args, **kwargs)

    def closed(self, code, reason=None):
        logging.debug('ws client: closed ({})'.format(code))
        self.connected = False

    def write_message(self, message):
        if self.connected:
            return self.send(message)
        logging.debug('ws client: queue message: {}'.format(message))
        self._queue.append(message)

    def _cleanup(self, *args, **kwargs):
        # FIXME: this seems clearly an error in ws4py.
        pass
