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
import sys

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


SSL_OPTIONS = {
    'certfile': '/etc/ssl/juju-gui/juju.crt',
    'keyfile': '/etc/ssl/juju-gui/juju.key',
}


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


def setup():
    """Set up options and logger."""
    define('guiroot', type=str, help='the Juju GUI static files path')
    define('jujuapi', type=str, help='the Juju WebSocket server address')
    # In Tornado, parsing the options also sets up the default logger.
    parse_command_line()
    _validate_required('guiroot', 'jujuapi')
    _add_debug(logging.getLogger())


def run():
    """Run the server"""
    server().listen(443, ssl_options=SSL_OPTIONS)
    redirector().listen(80)
    version = guiserver.get_version()
    logging.info('starting Juju GUI server v{}'.format(version))
    IOLoop.instance().start()
