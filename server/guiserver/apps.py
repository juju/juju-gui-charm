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

"""Juju GUI server applications."""

import os

from tornado import web
from tornado.options import options

from guiserver import (
    auth,
    handlers,
)


def server():
    """Return the main server application.

    The server app is responsible for serving the WebSocket connection, the
    Juju GUI static files and the main index file for dynamic URLs.
    """
    # Set up static paths.
    guiroot = options.guiroot
    static_path = os.path.join(guiroot, 'juju-ui')
    # Set up the authentication backend.
    auth_backend = auth.get_backend(options.apiversion)
    # Set up handlers.
    server_handlers = [
        # Handle WebSocket connections.
        (r'^/ws$', handlers.WebSocketHandler, {'apiurl': options.apiurl}),
        # Handle static files.
        (r'^/juju-ui/(.*)', web.StaticFileHandler, {'path': static_path}),
        (r'^/(favicon\.ico)$', web.StaticFileHandler, {'path': guiroot}),
    ]
    if options.servetests:
        params = {'path': options.servetests, 'default_filename': 'index.html'}
        server_handlers.append(
            # Serve the Juju GUI tests.
            (r'^/test/(.*)', web.StaticFileHandler, params),
        )
    server_handlers.append(
        # Any other path is served by index.html.
        (r'^/(.*)', handlers.IndexHandler, {'path': guiroot}),
    )
    return web.Application(
        server_handlers, debug=options.debug, auth_backend=auth_backend)


def redirector():
    """Return the redirector application.

    The redirector app is responsible for redirecting HTTP traffic to HTTPS.
    """
    return web.Application([
        # Redirect all HTTP traffic to HTTPS.
        (r'.*', handlers.HttpsRedirectHandler),
    ], debug=options.debug)
