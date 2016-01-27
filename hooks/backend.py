# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2012-2013 Canonical Ltd.
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

"""
A composition system for creating backend objects.

Backends implement install(), start() and stop() methods. A backend is composed
of many mixins and each mixin will implement any/all of those methods and all
will be called. Backends additionally provide for collecting property values
from each mixin into a single final property on the backend.

Mixins are not actually mixed in to the backend class using Python inheritance
machinery. Instead, each mixin is instantiated and collected in the Backend
__init__, as needed. Then the install(), start(), and stop() methods have a
"self" that is the simple instantiated mixin, and a "backend" argument that is
the backend instance. Python inheritance machinery is somewhat mimicked in that
certain properties and methods are explicitly aggregated on the backend
instance: see the call_methods function.

There is also a feature for determining if configuration values have changed
between old and new configurations so we can selectively take action.

The mixins appear in the code in the order they are instantiated by the
backend. Keeping them that way is useful.
"""

import errno
import os
import shutil

from charmhelpers import log
from shelltoolbox import run

import utils


class SetUpMixin(object):
    """Handle the overall set up and clean up processes."""

    def install(self, backend):
        log('Setting up base dir: {}.'.format(utils.BASE_DIR))
        try:
            os.makedirs(utils.BASE_DIR)
        except OSError as err:
            # The base directory might already exist: ignore the error.
            if err.errno != errno.EEXIST:
                raise

    def destroy(self, backend):
        log('Cleaning up base dir: {}.'.format(utils.BASE_DIR))
        shutil.rmtree(utils.BASE_DIR)


class GuiMixin(object):
    """Install and start the GUI and its dependencies."""

    # The curl package is used to download release tarballs from Launchpad.
    debs = ('curl',)

    def install(self, backend):
        """Install the GUI and dependencies."""
        # If the source setting has changed since the last time this was run,
        # get the code, from either a static release or a branch as specified
        # by the source setting, and install it.
        log('Installing juju gui.')
        utils.setup_gui()

    def start(self, backend):
        log('Starting Juju GUI.')
        # Set up TCP ports.
        previous_port = backend.prev_config.get('port')
        current_port = backend.config.get('port')
        utils.setup_ports(previous_port, current_port)


class GuiServerMixin(object):
    """Manage the builtin server via Upstart."""

    # The package openssl enables SSL support in Tornado.
    # The package python-bzrlib is required by juju-deployer.
    # The package python-pip is is used to install the GUI server dependencies.
    # The libcurl3 and python-pycurl packages are required so that the GUI
    # server can use Tornado's curl_httpclient.
    debs = (
        'libcurl3', 'openssl', 'python-bzrlib', 'python-pip', 'python-pycurl')

    def install(self, backend):
        utils.install_builtin_server()
        if backend.different(
                'ssl-cert-path', 'ssl-cert-contents', 'ssl-key-contents'):
            config = backend.config
            utils.save_or_create_certificates(
                config['ssl-cert-path'], config.get('ssl-cert-contents'),
                config.get('ssl-key-contents'))

    def start(self, backend):
        config = backend.config
        env_uuid = os.getenv('JUJU_ENV_UUID', None)
        juju_version = run('jujud', '--version').strip()
        utils.start_builtin_server(
            config['ssl-cert-path'], config['serve-tests'],
            config['sandbox'], config['builtin-server-logging'],
            not config['secure'], config['charmworld-url'],
            env_password=config.get('password'), env_uuid=env_uuid,
            juju_version=juju_version, debug=config['juju-gui-debug'],
            port=config.get('port'), jem_location=config['jem-location'],
            interactive_login=config['interactive-login'],
            gzip=config['gzip-compression'], gtm_enabled=config['gtm-enabled'])

    def stop(self, backend):
        utils.stop_builtin_server()


def call_methods(objects, name, *args):
    """For each given object, call, if present, the method named name.

    Pass the given args.
    """
    for obj in objects:
        method = getattr(obj, name, None)
        if method is not None:
            method(*args)


class Backend(object):
    """
    Support many configurations by composing methods and policy to interact
    with a Juju backend, collecting them from Strategy pattern mixin objects.
    """

    def __init__(self, config=None, prev_config=None):
        """Generate a list of mixin classes that implement the backend, working
        through composition.

        'config' is a dict which typically comes from the JSON de-serialization
            of config.json in JujuGUI.
        'prev_config' is a dict used to compute the differences. If it is not
            passed, all current config values are considered new.
        """
        if config is None:
            config = utils.get_config()
        self.config = config
        if prev_config is None:
            prev_config = {}
        self.prev_config = prev_config
        # XXX frankban: do we still need this mixin framework?
        self.mixins = [SetUpMixin(), GuiMixin(), GuiServerMixin()]

    def different(self, *keys):
        """Return a boolean indicating if the current config
        value differs from the config value passed in prev_config
        with respect to any of the passed in string keys.
        """
        # Minimize lookups inside the loop, just because.
        current, previous = self.config.get, self.prev_config.get
        return any(current(key) != previous(key) for key in keys)

    def get_dependencies(self):
        """Return a set of required dependencies."""
        debs = set()
        for mixin in self.mixins:
            debs.update(getattr(mixin, 'debs', ()))
        return debs

    def install(self):
        """Execute the installation steps."""
        log('Installing dependencies.')
        utils.install_missing_packages(self.get_dependencies())
        call_methods(self.mixins, 'install', self)

    def start(self):
        """Execute the charm's "start" steps."""
        call_methods(self.mixins, 'start', self)

    def stop(self):
        """Execute the charm's "stop" steps.

        Iterate through the mixins in reverse order.
        """
        call_methods(reversed(self.mixins), 'stop', self)

    def destroy(self):
        """Execute the charm removal steps.

        Iterate through the mixins in reverse order.
        """
        call_methods(reversed(self.mixins), 'destroy', self)
