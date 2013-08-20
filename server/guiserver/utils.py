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

"""Juju GUI server utility functions and classes."""

import collections
import errno
import logging
import os
import urlparse

from tornado import escape


def get_headers(request, websocket_url):
    """Return additional headers to be included in the client connection.

    Specifically this function includes in the returned dict the Origin
    header, taken from the provided browser request. If the origin is not found
    the HTTP(S) equivalent of the provided websocket address is returned.
    """
    origin = request.headers.get('Origin')
    if origin is None:
        origin = ws_to_http(websocket_url)
    return {'Origin': origin}


def json_decode_dict(message):
    """Decode the given JSON message, returning a Python dict.

    If the message is not a valid JSON string, or if the resulting object is
    not a dict-like object, log a warning and return None.
    """
    try:
        data = escape.json_decode(message)
    except ValueError:
        msg = 'JSON decoder: message is not valid JSON: {}'.format(message)
        logging.warning(msg)
        return None
    if not isinstance(data, collections.Mapping):
        msg = 'JSON decoder: message is not a dict: {}'.format(message)
        logging.warning(msg)
        return None
    return data


def mkdir(path):
    """Create a leaf directory and all intermediate ones.

    Also expand ~ and ~user constructions.
    If path exists and it's a directory, return without errors.
    """
    path = os.path.expanduser(path)
    try:
        os.makedirs(path)
    except OSError as err:
        # Re-raise the error if the target path exists but it is not a dir.
        if (err.errno != errno.EEXIST) or (not os.path.isdir(path)):
            raise


def request_summary(request):
    """Return a string representing a summary for the given request."""
    return '{} {} ({})'.format(request.method, request.uri, request.remote_ip)


def ws_to_http(url):
    """Return the HTTP(S) equivalent of the provided ws/wss URL."""
    parts = urlparse.urlsplit(url)
    scheme = {'ws': 'http', 'wss': 'https'}[parts.scheme]
    return '{}://{}{}'.format(scheme, parts.netloc, parts.path)
