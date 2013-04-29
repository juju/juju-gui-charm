"""
A composition system for creating backend object.

Backends implement start(), stop() and install() methods. A backend is composed
of many mixins and each mixin will implement any/all of those methods and all
will be called. Backends additionally provide for collecting property values
from each mixin into a single final property on the backend. There is also a
feature for determining if configuration values have changed between old and
new configurations so we can selectively take action.
"""

from charmhelpers import (
    RESTART,
    STOP,
    log,
    open_port,
    service_control,
)
from shelltoolbox import (
    apt_get_install,
    command,
    install_extra_repositories,
    su,
)
from utils import (
    AGENT,
    APACHE,
    HAPROXY,
    IMPROV,
    JUJU_DIR,
    chain,
    check_packages,
    cmd_log,
    fetch_api,
    fetch_gui,
    get_config,
    get_npm_cache_archive_url,
    legacy_juju,
    merge,
    overrideable,
    prime_npm_cache,
    save_or_create_certificates,
    setup_apache,
    setup_gui,
    start_agent,
    start_gui,
    start_improv,
)

import os
import shutil


apt_get = command('apt-get')


class InstallMixin(object):
    """Provide for the GUI and its dependencies to be installed."""

    def install(self, backend):
        """Install the GUI and dependencies."""
        config = backend.config
        # If the given installable thing ("backend") requires one or more debs
        # that are not yet installed, install them.
        missing = backend.check_packages(*backend.debs)
        if missing:
            cmd_log(backend.install_extra_repositories(*backend.repositories))
            cmd_log(apt_get_install(*backend.debs))

        # If we are not using a pre-built release of the GUI (i.e., we are
        # using a branch) then we need to build a release archive to use.
        if backend.different('juju-gui-source'):
            # Inject NPM packages into the cache for faster building.
            #prime_npm_cache(get_npm_cache_archive_url())
            # Build a release from the branch.
            release_tarball = fetch_gui(
                config['juju-gui-source'], config['command-log-file'])
            # XXX Why do we only set up the GUI if the "juju-gui-source"
            # configuration is non-default?
            setup_gui(release_tarball)


class UpstartMixin(object):
    """Manage (install, start, stop, etc.) some service via Upstart."""

    upstart_scripts = ('haproxy.conf', )
    debs = ('curl', 'openssl', 'haproxy', 'apache2')

    def install(self, backend):
        """Set up haproxy and nginx upstart configuration files."""
        setup_apache()
        backend.log('Setting up haproxy and nginx start up scripts.')
        config = backend.config
        if backend.different(
                'ssl-cert-path', 'ssl-cert-contents', 'ssl-key-contents'):
            save_or_create_certificates(
                config['ssl-cert-path'], config.get('ssl-cert-contents'),
                config.get('ssl-key-contents'))

        source_dir = os.path.join(os.path.dirname(__file__),  '..', 'config')
        for config_file in backend.upstart_scripts:
            shutil.copy(os.path.join(source_dir, config_file), '/etc/init/')

    def start(self, backend):
        with su('root'):
            backend.service_control(APACHE, RESTART)
            backend.service_control(HAPROXY, RESTART)

    def stop(self, backend):
        with su('root'):
            backend.service_control(HAPROXY, STOP)
            backend.service_control(APACHE, STOP)


class GuiMixin(object):
    gui_properties = set([
        'juju-gui-console-enabled', 'login-help', 'read-only',
        'serve-tests', 'secure'])

    repositories = ('ppa:juju-gui/ppa',)

    def start(self, config):
        start_gui(
            config['juju-gui-console-enabled'], config['login-help'],
            config['read-only'], config['staging'], config['ssl-cert-path'],
            config['charmworld-url'], config['serve-tests'],
            secure=config['secure'], sandbox=config['sandbox'])
        open_port(80)
        open_port(443)


class SandboxBackend(object):
    pass


class PythonBackend(object):

    def install(self, config):
        if (not os.path.exists(JUJU_DIR) or
                config.different('staging', 'juju-api-branch')):
            fetch_api(config['juju-api-branch'])

    def start(self, backend):
        backend.start_agent(backend['ssl-cert-path'])

    def stop(self, backend):
        backend.service_control(AGENT, STOP)


class ImprovBackend(object):
    debs = ('zookeeper', )

    def install(self, config):
        if (not os.path.exists(JUJU_DIR) or
                config.different('staging', 'juju-api-branch')):
            fetch_api(config['juju-api-branch'])

    def start(self, backend):
        backend.start_improv(
            backend['staging-environment'], backend['ssl-cert-path'])

    def stop(self, backend):
        backend.service_control(IMPROV, STOP)


class GoBackend(object):
    debs = ('python-yaml', )


class Backend(object):
    """Compose methods and policy needed to interact with a Juju backend.

    "config" is a config dict (which typically comes from the JSON
    de-serialization of config.json in JujuGUI).
    """

    def __init__(self, config=None, prev_config=None, **overrides):
        """Generate a selection of strategy classes that implement the backend.
        """
        # Ingest the config and build out the ordered list of
        # backend elements to include
        if config is None:
            config = get_config()
        self.config = config
        self.prev_config = prev_config
        self.overrides = overrides

        # We always install the GUI.
        backends = [InstallMixin, ]

        api = "python" if legacy_juju() else "go"
        sandbox = config.get('sandbox', False)
        staging = config.get('staging', False)

        if api == 'python':
            if staging:
                backends.append(ImprovBackend)
            elif sandbox:
                backends.append(SandboxBackend)
            else:
                backends.append(PythonBackend)
        else:
            if staging:
                raise ValueError(
                    "Unable to use staging with {} backend".format(api))
            if sandbox:
                raise ValueError(
                    "Unable to use sandbox with {} backend".format(api))
            backends.append(GoBackend)

        # All backends need to install, start, and stop the services that
        # provide the GUI.
        backends.append(GuiMixin)
        backends.append(UpstartMixin)

        # record our choice mapping classes to instances
        for i, b in enumerate(backends):
            if callable(b):
                backends[i] = b()
        self.backends = backends

    def __getitem__(self, key):
        try:
            return self.config[key]
        except KeyError:
            print("Unable to extract config key '%s' from %s" %
                (key, self.config))
            raise

    @overrideable
    def check_packages(self, *packages):
        return check_packages(*packages)

    @overrideable
    def service_control(self, service, action):
        service_control(service, action)

    @overrideable
    def start_agent(self, cert_path):
        start_agent(cert_path)

    @overrideable
    def start_improv(self, stage_env, cert_path):
        start_improv(stage_env, cert_path)

    @overrideable
    def log(self, msg, *args):
        log(msg, *args)

    @overrideable
    def install_extra_repositories(self, *packages):
        if self.config.get('allow-additional-deb-repositories', True):
            install_extra_repositories(*packages)
        else:
            apt_get('update')

    def different(self, *keys):
        """Return a boolean indicating if the current config
        value differs from the config value passed in prev_config
        with respect to any of the passed in string keys.
        """
        if self.prev_config is None:
            return True

        for key in keys:
            current = self.config.get(key)
            prev = self.prev_config.get(key)
            r = current != prev
            if r:
                return True
        return False

    ## Composed Methods
    install = chain('install')
    start = chain('start')
    stop = chain('stop')

    ## Merged Properties
    dependencies = merge('dependencies')
    build_dependencies = merge('build_dependencies')
    staging_dependencies = merge('staging_dependencies')

    repositories = merge('repositories')
    debs = merge('debs')
    upstart_scripts = merge('upstart_scripts')
