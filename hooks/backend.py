"""
A composition system for creating backend object.

Backends implement start(), stop() and install() methods. A backend is composed
of many mixins and each mixin will implement any/all of those methods and all
will be called. Backends additionally provide for collecting property values
from each mixin into a single final property on the backend. There is also a
feature for determining if configuration values have changed between old and
new configurations so we can selectively take action.
"""

import charmhelpers
import shelltoolbox
import utils

import os
import shutil


apt_get = shelltoolbox.command('apt-get')
SYS_INIT_DIR = '/etc/init/'


class InstallMixin(object):
    def install(self, backend):
        config = backend.config
        missing = utils.check_packages(*backend.debs)
        if missing:
            utils.cmd_log(
                backend.install_extra_repositories(*backend.repositories))
            utils.cmd_log(
                shelltoolbox.apt_get_install(*backend.debs))

        if backend.different('juju-gui-source'):
            release_tarball = utils.fetch_gui(
                config['juju-gui-source'], config['command-log-file'])
            utils.setup_gui(release_tarball)


class UpstartMixin(object):
    upstart_scripts = ('haproxy.conf', )
    debs = ('curl', 'openssl', 'haproxy', 'apache2')

    def install(self, backend):
        """Set up haproxy and nginx upstart configuration files."""
        utils.setup_apache()
        charmhelpers.log('Setting up haproxy and nginx start up scripts.')
        config = backend.config
        if backend.different(
                'ssl-cert-path', 'ssl-cert-contents', 'ssl-key-contents'):
            utils.save_or_create_certificates(
                config['ssl-cert-path'], config.get('ssl-cert-contents'),
                config.get('ssl-key-contents'))

        source_dir = os.path.join(os.path.dirname(__file__),  '..', 'config')
        for config_file in backend.upstart_scripts:
            shutil.copy(os.path.join(source_dir, config_file), SYS_INIT_DIR)

    def start(self, backend):
        with shelltoolbox.su('root'):
            charmhelpers.service_control(utils.APACHE, charmhelpers.RESTART)
            charmhelpers.service_control(utils.HAPROXY, charmhelpers.RESTART)

    def stop(self, backend):
        with shelltoolbox.su('root'):
            charmhelpers.service_control(utils.HAPROXY, charmhelpers.STOP)
            charmhelpers.service_control(utils.APACHE, charmhelpers.STOP)


class GuiMixin(object):
    repositories = ('ppa:juju-gui/ppa',)

    def start(self, backend):
        config = backend.config
        utils.start_gui(
            config['juju-gui-console-enabled'], config['login-help'],
            config['read-only'], config['staging'], config['ssl-cert-path'],
            config['charmworld-url'], config['serve-tests'],
            secure=config['secure'], sandbox=config['sandbox'])
        charmhelpers.open_port(80)
        charmhelpers.open_port(443)


class SandboxMixin(object):
    pass


class PythonMixin(object):

    def install(self, backend):
        config = backend.config
        if (not os.path.exists(utils.JUJU_DIR) or
                backend.different('staging', 'juju-api-branch')):
            utils.fetch_api(config['juju-api-branch'])

    def start(self, backend):
        utils.start_agent(backend.config['ssl-cert-path'])

    def stop(self, backend):
        charmhelpers.service_control(utils.AGENT, charmhelpers.STOP)


class ImprovMixin(object):
    debs = ('zookeeper', )

    def install(self, backend):
        config = backend.config
        if (not os.path.exists(utils.JUJU_DIR) or
                backend.different('staging', 'juju-api-branch')):
            utils.fetch_api(config['juju-api-branch'])

    def start(self, backend):
        config = backend.config
        utils.start_improv(
            config['staging-environment'], config['ssl-cert-path'])

    def stop(self, backend):
        charmhelpers.service_control(utils.IMPROV, charmhelpers.STOP)


class GoMixin(object):
    debs = ('python-yaml', )


class Backend(object):
    """Compose methods and policy needed to interact with a Juju backend.

    Mixins work through composition. __init__ is a factory that generates
    a list of mixin classes to use together to implement the backend proper.
    """

    def __init__(self, config=None, prev_config=None):
        """
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

        mixins = [InstallMixin]

        sandbox = config.get('sandbox', False)
        staging = config.get('staging', False)

        if utils.legacy_juju():
            if staging:
                mixins.append(ImprovMixin)
            elif sandbox:
                mixins.append(SandboxMixin)
            else:
                mixins.append(PythonMixin)
        else:
            if staging:
                raise ValueError('Unable to use staging with go backend')
            elif sandbox:
                raise ValueError('Unable to use sandbox with go backend')
            mixins.append(GoMixin)

        # All mixins can manage the GUI.
        mixins.append(GuiMixin)
        # We always use upstart.
        mixins.append(UpstartMixin)

        # record our choice mapping classes to instances
        for i, b in enumerate(mixins):
            if callable(b):
                mixins[i] = b()
        self.mixins = mixins

    def install_extra_repositories(self, *packages):
        if self.config.get('allow-additional-deb-repositories', True):
            utils.install_extra_repositories(*packages)
        else:
            apt_get('update')

    def different(self, *keys):
        """Return a boolean indicating if the current config
        value differs from the config value passed in prev_config
        with respect to any of the passed in string keys.
        """
        return any(self.config.get(key) != self.prev_config.get(key)
            for key in keys)

    ## Composed Methods
    install = utils.chain('install')
    start = utils.chain('start')
    stop = utils.chain('stop')

    ## Merged Properties
    dependencies = utils.merge('dependencies')
    build_dependencies = utils.merge('build_dependencies')
    staging_dependencies = utils.merge('staging_dependencies')

    repositories = utils.merge('repositories')
    debs = utils.merge('debs')
    upstart_scripts = utils.merge('upstart_scripts')
