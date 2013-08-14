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

import json

from tornado import websocket
import yaml

from guiserver import auth


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


class GoAPITestMixin(object):
    """Add helper methods for testing the Go API implementation."""

    def get_auth_backend(self):
        """Return an authentication backend suitable for the Go API."""
        return auth.get_backend('go')

    def make_login_request(
            self, request_id=42, username='user', password='passwd',
            encoded=False):
        """Create and return a login request message.

        If encoded is set to True, the returned message will be JSON encoded.
        """
        data = {
            'RequestId': request_id,
            'Type': 'Admin',
            'Request': 'Login',
            'Params': {'AuthTag': username, 'Password': password},
        }
        return json.dumps(data) if encoded else data

    def make_login_response(
            self, request_id=42, successful=True, encoded=False):
        """Create and return a login response message.

        If encoded is set to True, the returned message will be JSON encoded.
        By default, a successful response is returned. Set successful to False
        to return an authentication failure.
        """
        data = {'RequestId': request_id, 'Response': {}}
        if not successful:
            data['Error'] = 'invalid entity name or password'
        return json.dumps(data) if encoded else data


class PythonAPITestMixin(object):
    """Add helper methods for testing the Python API implementation."""

    def get_auth_backend(self):
        """Return an authentication backend suitable for the Python API."""
        return auth.get_backend('python')

    def make_login_request(
            self, request_id=42, username='user', password='passwd',
            encoded=False):
        """Create and return a login request message.

        If encoded is set to True, the returned message will be JSON encoded.
        """
        data = {
            'request_id': request_id,
            'op': 'login',
            'user': username,
            'password': password,
        }
        return json.dumps(data) if encoded else data

    def make_login_response(
            self, request_id=42, successful=True, encoded=False):
        """Create and return a login response message.

        If encoded is set to True, the returned message will be JSON encoded.
        By default, a successful response is returned. Set successful to False
        to return an authentication failure.
        """
        data = {'request_id': request_id, 'op': 'login'}
        if successful:
            data['result'] = True
        else:
            data['err'] = True
        return json.dumps(data) if encoded else data


class BundlesTestMixin(object):
    """Add helper methods for testing the GUI server bundles support."""

    bundle = """
        envExport:
          series: precise
          services:
            wordpress:
              charm: "cs:precise/wordpress-15"
              num_units: 1
              options:
                debug: "no"
                engine: nginx
                tuning: single
                "wp-content": ""
              annotations:
                "gui-x": 313
                "gui-y": 51
            mysql:
              charm: "cs:precise/mysql-26"
              num_units: 1
              options:
                "binlog-format": MIXED
                "block-size": "5"
                "dataset-size": "80%"
                flavor: distro
                "ha-bindiface": eth0
                "ha-mcastport": "5411"
                "max-connections": "-1"
                "preferred-storage-engine": InnoDB
                "query-cache-size": "-1"
                "query-cache-type": "OFF"
                "rbd-name": mysql1
                "tuning-level": safest
                vip: ""
                vip_cidr: "24"
                vip_iface: eth0
              annotations:
                "gui-x": 669.5
                "gui-y": -33.5
          relations:
            - - "wordpress:db"
              - "mysql:db"
    """

    def get_name_and_bundle(self):
        """Return a tuple (bundle name, contents) parsing self.bundle."""
        all_contents = yaml.load(self.bundle)
        name = all_contents.keys()[0]
        return name, all_contents[name]


class WSSTestMixin(object):
    """Add some helper methods for testing secure WebSocket handlers."""

    def get_wss_url(self, path):
        """Return an absolute secure WebSocket url for the given path."""
        return 'wss://localhost:{}{}'.format(self.get_http_port(), path)
