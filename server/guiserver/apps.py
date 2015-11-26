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
from ConfigParser import RawConfigParser
import os
import time

from pyramid.config import Configurator
from tornado import web
from tornado.options import options
from tornado.wsgi import WSGIContainer

from guiserver import (
    auth,
    handlers,
    utils,
)
from guiserver.bundles.base import Deployer
from jujugui import make_application

INI_PATH = '/home/ubuntu/production.ini'


def server():
    """Return the main server application.

    The server app is responsible for serving the WebSocket connection, the
    Juju GUI static files and the main index file for dynamic URLs.
    """
    # Set up the bundle deployer.
    deployer = Deployer(options.apiurl, options.apiversion,
                        options.charmworldurl)
    # Set up handlers.
    server_handlers = []
    if options.sandbox:
        # Sandbox mode.
        server_handlers.append(
            (r'^/ws(?:/.*)?$', handlers.SandboxHandler, {}))
    else:
        # Real environment.
        tokens = auth.AuthenticationTokenHandler()
        websocket_handler_options = {
            # The Juju API backend url.
            'apiurl': options.apiurl,
            # The backend to use for user authentication.
            'auth_backend': auth.get_backend(options.apiversion),
            # The Juju deployer to use for importing bundles.
            'deployer': deployer,
            # The tokens collection for authentication token requests.
            'tokens': tokens,
        }
        juju_proxy_handler_options = {
            'target_url': utils.ws_to_http(options.apiurl),
            'charmworld_url': options.charmworldurl,
        }
        server_handlers.extend([
            # Handle WebSocket connections.
            (r'^/ws(?:/.*)?$', handlers.WebSocketHandler,
                websocket_handler_options),
            # Handle connections to the juju-core HTTPS server.
            # The juju-core HTTPS and WebSocket servers share the same URL.
            (r'^/juju-core/(.*)', handlers.JujuProxyHandler,
             juju_proxy_handler_options),
        ])
    if options.testsroot:
        params = {'path': options.testsroot, 'default_filename': 'index.html'}
        server_handlers.append(
            # Serve the Juju GUI tests.
            (r'^/test/(.*)', web.StaticFileHandler, params),
        )
    info_handler_options = {
        'apiurl': options.apiurl,
        'apiversion': options.apiversion,
        'deployer': deployer,
        'sandbox': options.sandbox,
        'start_time': int(time.time()),
    }
    settings = RawConfigParser()
    settings.read(INI_PATH)
    config = Configurator(settings=dict(settings.items('app:main')))
    wsgi_app = WSGIContainer(make_application(config))
    server_handlers.extend([
        # Handle GUI server info.
        (r'^/gui-server-info', handlers.InfoHandler, info_handler_options),
        (r".*", web.FallbackHandler, dict(fallback=wsgi_app))
    ])

    server_handlers.extend([
    ])
    return web.Application(server_handlers, debug=options.debug)


def redirector():
    """Return the redirector application.

    The redirector app is responsible for redirecting HTTP traffic to HTTPS.
    """
    return web.Application([
        # Redirect all HTTP traffic to HTTPS.
        (r'.*', handlers.HttpsRedirectHandler),
    ], debug=options.debug)
