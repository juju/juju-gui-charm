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

from lib import handlers


def server():
    """Return the main server application.

    The server app is responsible for serving the WebSocket connection, the
    Juju GUI static files and the main index file for dynamic URLs.
    """
    # Avoid module level import so that options can be properly set up.
    from tornado.options import options
    static_path = os.path.join(options.guiroot, 'juju-ui')
    return web.Application([
        # Handle WebSocket connections.
        (r'/ws', handlers.WebSocketHandler),
        # Handle static files.
        (r'/juju-ui/(.*)', web.StaticFileHandler, {'path': static_path}),
        (r'/(favicon\.ico)', web.StaticFileHandler, {'path': options.guiroot}),
        # Any other path is served by index.html.
        (r'/(.*)', handlers.IndexHandler, {'path': options.guiroot}),
    ], debug=options.debug)


def redirector():
    """Return the redirector application.

    The redirector app is responsible for redirecting HTTP traffic to HTTPS.
    """
    # Avoid module level import so that options can be properly set up.
    from tornado.options import options
    return web.Application([
        # Redirect all HTTP traffic to HTTPS.
        (r'.*', handlers.HttpsRedirectHandler),
    ], debug=options.debug)
