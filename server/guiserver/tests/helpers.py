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
import multiprocessing
import os
import signal

import mock
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
        return all_contents.items()[0]

    def make_view_request(self, params=None, is_authenticated=True):
        """Create and return a mock request to be passed to bundle views.

        The resulting request contains the given parameters and a
        guiserver.auth.User instance.
        If is_authenticated is True, the user in the request is logged in.
        """
        if params is None:
            params = {}
        user = auth.User(
            username='user', password='passwd',
            is_authenticated=is_authenticated)
        return mock.Mock(params=params, user=user)


class WSSTestMixin(object):
    """Add some helper methods for testing secure WebSocket handlers."""

    def get_wss_url(self, path):
        """Return an absolute secure WebSocket url for the given path."""
        return 'wss://localhost:{}{}'.format(self.get_http_port(), path)


class MultiProcessMock(object):
    """Return a callable mock object to be used across multiple processes.

    In a multiprocess context the usual mock.Mock() does not work as expected:
    see <https://code.google.com/p/mock/issues/detail?id=139>.

    Help sharing call info between separate processes, and ensuring that the
    callable is called in a separate process.
    Note that only self.__call__() must be executed in a separate process: all
    the other methods are supposed to be called in the main process.
    """

    def __init__(self, side_effect=None):
        """Initialize the mock object.

        Calling this object will return side_effect if it is not an exception.
        If otherwise side_effect is an exception, that error will be raised.
        """
        # When testing across multiple processes, a SIGPIPE can intermittently
        # generate a broken pipe IOError. In order to avoid that, restore the
        # default handler for the SIGPIPE signal when initializing this mock.
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        self.side_effect = side_effect
        manager = multiprocessing.Manager()
        self.queue = manager.Queue()
        self._call_pids = []
        self._call_args = []

    def __call__(self, *args, **kwargs):
        """Return or raise self.side_effect.

        This method is supposed to be called in a separate process.
        """
        side_effect = self.side_effect
        self.queue.put((os.getpid(), args, kwargs))
        if isinstance(side_effect, Exception):
            raise side_effect
        return side_effect

    def _consume_queue(self):
        """Collect info about how this mock has been called."""
        while not self.queue.empty():
            pid, args, kwargs = self.queue.get()
            self._call_pids.append(pid)
            self._call_args.append((args, kwargs))

    @property
    def call_args(self):
        """Return a list of (args, kwargs) tuples.

        Each pair in the list represents the arguments of a single call.
        """
        self._consume_queue()
        return self._call_args

    @property
    def call_count(self):
        """Return the number of times this mock has been called."""
        return len(self.call_args)

    def assert_called_once_with(self, *args, **kwargs):
        """Ensure this mock has been called once with the given arguments."""
        # Check call count.
        call_count = self.call_count
        if self.call_count != 1:
            error = 'Expected to be called once. Called {} times.'
            raise AssertionError(error.format(call_count))
        # Check call args.
        expected = (args, kwargs)
        obtained = self._call_args[0]
        if expected != obtained:
            error = (
                'Called with different arguments.\n'
                'Expected: {}\nObtained: {}'.format(expected, obtained)
            )
            raise AssertionError(error)

    def assert_called_in_a_separate_process(self):
        """Ensure this object was called in a separate process."""
        assert self.call_count, 'Not even called.'
        pid = self._call_pids[-1]
        assert pid != os.getpid(), 'Called in the same process: {}'.format(pid)
