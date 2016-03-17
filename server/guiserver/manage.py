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

"""Juju GUI server management."""

import logging
import os
import sys

from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop
from tornado.options import (
    define,
    options,
    parse_command_line,
)

import guiserver
from guiserver.apps import (
    redirector,
    server,
)


DEFAULT_API_VERSION = 'go'
DEFAULT_SSL_PATH = '/etc/ssl/juju-gui'


def _add_debug(logger):
    """Add a debug option to the option parser.

    The debug option is True if --logging=DEBUG is passed, False otherwise.
    """
    debug = logger.level == logging.DEBUG
    options.define('debug', default=debug)


def _validate_required(*args):
    """Validate required arguments.

    Exit with an error if a mandatory argument is missing.
    """
    for name in args:
        try:
            value = options[name].strip()
        except AttributeError:
            value = ''
        if not value:
            sys.exit('error: the {} argument is required'.format(name))


def _validate_choices(option_name, choices):
    """Ensure the value passed for the given option is included in the choices.

    Exit with an error if the value is not in the accepted ones.
    """
    value = options[option_name]
    if value not in choices:
        sys.exit('error: accepted values for the {} argument are: {}'.format(
            option_name, ', '.join(choices)))


def _validate_range(option_name, min_value, max_value):
    """Ensure the numeric value passed for the given option is in range.

    The range is defined by min_value and max_value.
    Exit with an error if the value is not in the given range.
    """
    value = options[option_name]
    if (value is not None) and not (min_value <= value <= max_value):
        sys.exit('error: the {} argument must be included between '
                 '{} and {}'.format(option_name, min_value, max_value))


def _get_ssl_options():
    """Return a Tornado SSL options dict.

    The certificate and key file paths are generated using the base SSL path
    included in the options.
    """
    return {
        'certfile': os.path.join(options.sslpath, 'juju.crt'),
        'keyfile': os.path.join(options.sslpath, 'juju.key'),
    }


def setup():
    """Set up options and logger. Configure the asynchronous HTTP client."""
    define(
        'apiurl', type=str,
        help='The Juju WebSocket server address. This is usually the address '
             'of the bootstrap/state node as returned by "juju status".')
    # Optional parameters.
    define(
        'apiversion', type=str, default=DEFAULT_API_VERSION,
        help='the Juju API version/implementation. Currently the possible '
             'values are "go" (default) or "python".')
    define(
        'testsroot', type=str,
        help='The filesystem path of the Juju GUI tests directory. '
             'If not provided, tests are not served.')
    define(
        'sslpath', type=str, default=DEFAULT_SSL_PATH,
        help='The path where the SSL certificates are stored.')
    define(
        'insecure', type=bool, default=False,
        help='Set to True to serve the GUI over an insecure HTTP connection. '
             'Do not set unless you understand and accept the risks.')
    define(
        'sandbox', type=bool, default=False,
        help='Set to True if the GUI is running in sandbox mode, i.e. using '
             'an in-memory backend. When this is set to True, the GUI server '
             'does not listen to incoming WebSocket connections, and '
             'therefore the --apiurl and --apiversion options are ignored.')
    define(
        'charmworldurl', type=str,
        help='The URL to use for Charmworld.')
    define(
        'port', type=int,
        help='User defined port to run the server on. If no port is defined '
             'the server will be started on 80 and 443 as per the default '
             'port options from the charm.')
    define(
        'jujuguidebug', type=bool, default=False,
        help='Set to True to run the gui without minifiying or combining '
             'source files.')
    define('user', type=str, help='The juju environment user.')
    define('password', type=str, help='The juju environment password.')
    define('uuid', type=str, help='The juju environment uuid.')
    define('jujuversion', type=str, help='The jujud version.')
    define(
        'charmstoreurl', type=str,
        default='https://api.jujucharms.com/charmstore/',
        help="The url for the charmstore.")
    define(
        'charmstoreversion', type=str, default='v4',
        help="The version of the charmstore API to use.")
    define(
        'jemlocation', type=str,
        help="The url for a Juju Environment Manager.")
    define(
        'jemversion', type=str, default='v1',
        help="The version of the JEM API to use.")
    define(
        'interactivelogin', type=bool, default=False,
        help='Enables interactive login to identity manager, if applicable.')
    define(
        'gzip', type=bool, default=False,
        help='Enable gzip compression in the gui.')
    define('gtm', type=bool, default=False, help='Enable Google tag manager.')
    # In Tornado, parsing the options also sets up the default logger.
    parse_command_line()
    _validate_choices('apiversion', ('go', 'python'))
    _validate_range('port', 1, 65535)
    _add_debug(logging.getLogger())
    # Configure the asynchronous HTTP client used by proxy handlers.
    AsyncHTTPClient.configure(
        'tornado.curl_httpclient.CurlAsyncHTTPClient', max_clients=20)


def run():
    """Run the server"""
    port = options.port
    if options.insecure:
        # Run the server over an insecure HTTP connection.
        if port is None:
            port = 80
        server().listen(port)
    else:
        # Default configuration: run the server over a secure HTTPS connection.
        if port is None:
            port = 443
            redirector().listen(80)
        server().listen(port, ssl_options=_get_ssl_options())
    version = guiserver.get_version()
    logging.info('starting Juju GUI server v{}'.format(version))
    logging.info('listening on port {}'.format(port))
    IOLoop.instance().start()
