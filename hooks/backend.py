"""
A composition system for creating backend objects.

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
    legacy_juju,
    merge,
    overrideable,
    save_or_create_certificates,
    setup_gui,
    setup_apache,
    start_agent,
    start_gui,
    start_improv,
)

import os
import shutil


apt_get = command('apt-get')


class InstallMixin(object):

    def install(self, backend):
        config = backend.config
        missing = backend.check_packages(*backend.debs)
        if missing:
            cmd_log(backend.install_extra_repositories(*backend.repositories))
            cmd_log(apt_get_install(*backend.debs))

        if backend.different('juju-gui-source'):
            release_tarball = fetch_gui(
                config['juju-gui-source'], config['command-log-file'])
            setup_gui(release_tarball)


class GuiMixin(object):
    repositories = ('ppa:juju-gui/ppa',)

    def start(self, backend):
        config = backend.config
        start_gui(
            config['juju-gui-console-enabled'], config['login-help'],
            config['read-only'], config['staging'], config['ssl-cert-path'],
            config['charmworld-url'], config['serve-tests'],
            secure=config['secure'], sandbox=config['sandbox'])
        open_port(80)
        open_port(443)


class UpstartMixin(object):
    upstart_scripts = ('haproxy.conf', )
    debs = ('curl', 'openssl', 'haproxy', 'apache2')

    def install(self, backend):
        """Set up haproxy and Apache upstart configuration files."""
        setup_apache()
        backend.log('Setting up haproxy and Apache start up scripts.')
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
    """Compose methods and policy needed to interact
    with a Juju backend. Given a config dict (which typically
    comes from the JSON de-serialization of config.json in JujuGUI).
    """

    def __init__(self, config=None, prev_config=None, **overrides):
        """
        Backends function through composition. __init__ becomes the
        factory method to generate a selection of strategy classes
        to use together to implement the backend proper.
        """
        # Ingest the config and build out the ordered list of backend elements
        # to include.
        if config is None:
            config = get_config()
        self.config = config
        if prev_config is None:
            prev_config = {}
        self.prev_config = prev_config
        self.overrides = overrides

        mixins = [InstallMixin]

        sandbox = config.get('sandbox', False)
        staging = config.get('staging', False)

        if legacy_juju():
            if staging:
                mixins.append(ImprovBackend)
            elif sandbox:
                mixins.append(SandboxBackend)
            else:
                mixins.append(PythonBackend)
        else:
            if staging:
                raise ValueError('Unable to use staging with go backend')
            elif sandbox:
                raise ValueError('Unable to use sandbox with go backend')
            mixins.append(GoBackend)

        # All mixins can manage the GUI.
        mixins.append(GuiMixin)
        # We always use upstart.
        mixins.append(UpstartMixin)

        # Record our choice mapping classes to instances.
        for i, b in enumerate(mixins):
            if callable(b):
                mixins[i] = b()
        self.mixins = mixins

    # def __getitem__(self, key):
    #     try:
    #         return self.config[key]
    #     except KeyError:
    #         print('Unable to extract config key "%s" from %s' %
    #             (key, self.config))
    #         raise

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
        if any(self.config.get(key) != self.prev_config.get(key)
                for key in keys):
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
