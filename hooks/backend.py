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
instance: see the chain_methods and merge_properties functions, and their
usages.

There is also a feature for determining if configuration values have changed
between old and new configurations so we can selectively take action.

The mixins appear in the code in the order they are instantiated by the
backend. Keeping them that way is useful.
"""

import os
import shutil

import charmhelpers
import shelltoolbox

import utils


apt_get = shelltoolbox.command('apt-get')
SYS_INIT_DIR = '/etc/init/'
TORNADO_TARBALL = 'tornado-3.1.tar.gz'


class PythonInstallMixinBase(object):
    """Provide a common "install" method to ImprovMixin and PythonMixin."""

    def install(self, backend):
        config = backend.config
        if (not os.path.exists(utils.JUJU_DIR) or
                backend.different('staging', 'juju-api-branch')):
            utils.fetch_api(config['juju-api-branch'])


class ImprovMixin(PythonInstallMixinBase):
    """Manage the improv backend when on staging."""

    debs = ('zookeeper',)

    def start(self, backend):
        config = backend.config
        utils.start_improv(
            config['staging-environment'], config['ssl-cert-path'])

    def stop(self, backend):
        charmhelpers.service_control(utils.IMPROV, charmhelpers.STOP)


class SandboxMixin(object):
    pass


class PythonMixin(PythonInstallMixinBase):
    """Manage the real PyJuju backend."""

    def start(self, backend):
        utils.start_agent(backend.config['ssl-cert-path'])

    def stop(self, backend):
        charmhelpers.service_control(utils.AGENT, charmhelpers.STOP)


class GoMixin(object):
    """Manage the real Go juju-core backend."""

    debs = ('python-yaml',)

    def install(self, backend):
        # When juju-core deploys the charm, the charm directory (which hosts
        # the GUI itself) is permissioned too strictly; set the perms on that
        # directory to be friendly for Apache.
        # Bug: 1202772
        utils.cmd_log(shelltoolbox.run('chmod', '+x', utils.CURRENT_DIR))


class GuiMixin(object):
    """Install and start the GUI and its dependencies."""

    debs = ('curl',)

    def install(self, backend):
        """Install the GUI and dependencies."""
        # If the given installable thing ("backend") requires one or more debs
        # that are not yet installed, install them.
        missing = utils.find_missing_packages(*backend.debs)
        if missing:
            utils.cmd_log(
                shelltoolbox.apt_get_install(*backend.debs))
        # If the source setting has changed since the last time this was run,
        # get the code, from either a static release or a branch as specified
        # by the souce setting, and install it.
        if backend.different('juju-gui-source'):
            # Get a tarball somehow.
            logpath = backend.config['command-log-file']
            origin, version_or_branch = utils.parse_source(
                backend.config['juju-gui-source'])
            if origin == 'branch':
                branch_url, revision = version_or_branch
                release_tarball_path = utils.fetch_gui_from_branch(
                    branch_url, revision, logpath)
            else:
                release_tarball_path = utils.fetch_gui_release(
                    origin, version_or_branch)
            # Install the tarball.
            utils.setup_gui(release_tarball_path)

    def start(self, backend):
        charmhelpers.log('Starting Juju GUI.')
        config = backend.config
        build_dir = utils.compute_build_dir(
            config['staging'], config['serve-tests'])
        utils.write_gui_config(
            config['juju-gui-console-enabled'], config['login-help'],
            config['read-only'], config['staging'], config['charmworld-url'],
            build_dir, secure=config['secure'], sandbox=config['sandbox'],
            use_analytics=config['use-analytics'],
            default_viewmode=config['default-viewmode'],
            show_get_juju_button=config['show-get-juju-button'])
        # TODO: eventually this option will go away, as well as haproxy and
        # Apache.
        if config['builtin-server']:
            api_version = 'python' if utils.legacy_juju() else 'go'
            utils.write_builtin_server_startup(
                utils.JUJU_GUI_DIR, utils.get_api_address(),
                api_version=api_version, serve_tests=config['serve-tests'],
                ssl_path=config['ssl-cert-path'],
                insecure=not config['secure'])
        else:
            utils.write_haproxy_config(
                config['ssl-cert-path'], secure=config['secure'])
            utils.write_apache_config(build_dir, config['serve-tests'])
        # Expose the service.
        charmhelpers.open_port(80)
        charmhelpers.open_port(443)


class ServerInstallMixinBase(object):
    """
    Provide a common "_post_install" method to HaproxyApacheMixin and
    BuiltinServerMixin.
    """

    def _post_install(self, backend):
        config = backend.config
        if backend.different(
                'ssl-cert-path', 'ssl-cert-contents', 'ssl-key-contents'):
            utils.save_or_create_certificates(
                config['ssl-cert-path'], config.get('ssl-cert-contents'),
                config.get('ssl-key-contents'))
        charmhelpers.log('Setting up startup scripts.')
        source_dir = os.path.join(os.path.dirname(__file__),  '..', 'config')
        for config_file in backend.upstart_scripts:
            shutil.copy(os.path.join(source_dir, config_file), SYS_INIT_DIR)


class HaproxyApacheMixin(ServerInstallMixinBase):
    """Manage haproxy and Apache via Upstart."""

    upstart_scripts = ('haproxy.conf',)
    debs = ('openssl', 'haproxy', 'apache2')

    def install(self, backend):
        """Set up haproxy and Apache startup configuration files."""
        utils.setup_apache()
        self._post_install(backend)

    def start(self, backend):
        with shelltoolbox.su('root'):
            charmhelpers.service_control(utils.APACHE, charmhelpers.RESTART)
            charmhelpers.service_control(utils.HAPROXY, charmhelpers.RESTART)

    def stop(self, backend):
        with shelltoolbox.su('root'):
            charmhelpers.service_control(utils.HAPROXY, charmhelpers.STOP)
            charmhelpers.service_control(utils.APACHE, charmhelpers.STOP)


class BuiltinServerMixin(ServerInstallMixinBase):
    """Manage the builtin server via Upstart."""

    debs = ('openssl', 'python-pip')

    def install(self, backend):
        """Set up the builtin server startup configuration file."""
        # Install Tornado from a local tarball.
        tornado_path = os.path.join(
            os.path.dirname(__file__),  '..', 'deps', TORNADO_TARBALL)
        shelltoolbox.run('pip', 'install', tornado_path)
        self._post_install(backend)

    def start(self, backend):
        with shelltoolbox.su('root'):
            charmhelpers.service_control(
                utils.BUILTIN_SERVER, charmhelpers.RESTART)

    def stop(self, backend):
        with shelltoolbox.su('root'):
            charmhelpers.service_control(
                utils.BUILTIN_SERVER, charmhelpers.STOP)


def chain_methods(name):
    """Helper to compose a set of mixin objects into a callable.

    Each method is called in the context of its mixin instance, and its
    argument is the Backend instance.
    """
    # Chain method calls through all implementing mixins.
    def method(self):
        for mixin in self.mixins:
            a_callable = getattr(type(mixin), name, None)
            if a_callable is not None:
                a_callable(mixin, self)
    method.__name__ = name
    return method


def merge_properties(name):
    """Helper to merge one property from mixin objects into a unified set."""
    @property
    def method(self):
        result = set()
        for mixin in self.mixins:
            result |= set(getattr(type(mixin), name, frozenset()))
        return result
    return method


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
        self.mixins = []

        sandbox = config['sandbox']
        staging = config['staging']

        if utils.legacy_juju():
            if staging:
                self.mixins.append(ImprovMixin())
            elif sandbox:
                self.mixins.append(SandboxMixin())
            else:
                self.mixins.append(PythonMixin())
        else:
            if staging:
                raise ValueError('Unable to use staging with go backend')
            elif sandbox:
                raise ValueError('Unable to use sandbox with go backend')
            self.mixins.append(GoMixin())

        # All backends need to install, start, and stop the services that
        # provide the GUI.
        self.mixins.append(GuiMixin())
        # TODO: eventually this option will go away, as well as haproxy and
        # Apache.
        if config['builtin-server']:
            self.mixins.append(BuiltinServerMixin())
        else:
            self.mixins.append(HaproxyApacheMixin())

    def different(self, *keys):
        """Return a boolean indicating if the current config
        value differs from the config value passed in prev_config
        with respect to any of the passed in string keys.
        """
        # Minimize lookups inside the loop, just because.
        current, previous = self.config.get, self.prev_config.get
        return any(current(key) != previous(key) for key in keys)

    # Composed methods.
    install = chain_methods('install')
    start = chain_methods('start')
    stop = chain_methods('stop')

    # Merged properties.
    dependencies = merge_properties('dependencies')
    build_dependencies = merge_properties('build_dependencies')
    staging_dependencies = merge_properties('staging_dependencies')

    repositories = merge_properties('repositories')
    debs = merge_properties('debs')
    upstart_scripts = merge_properties('upstart_scripts')
