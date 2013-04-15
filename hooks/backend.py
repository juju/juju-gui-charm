## These normally depend on python packages being installed
## from hooks/install. If we are unable to use external code
## due to some  deployment restrictions these deps will already
## have been installed or this code will fail.
from charmhelpers import (
    log,
    open_port,
    service_control,
    RESTART,
    STOP,
)
from shelltoolbox import (
    apt_get_install,
    install_extra_repositories,
    su,
)

from utils import (
    AGENT,
    HAPROXY,
    IMPROV,
    JUJU_DIR,
    NGINX,
    chain,
    check_packages,
    cmd_log,
    fetch_api,
    fetch_gui,
    get_config,
    legacy_juju,
    merge,
    overrideable,
    parse_source,
    save_or_create_certificates,
    setup_gui,
    setup_nginx,
    start_agent,
    start_gui,
    start_improv,
)

import os
import shutil


class InstallMixin(object):
    def install(self, backend):
        config = backend.config
        allow_external = backend['allow-external-sources']
        missing = backend.check_packages(*backend.debs)
        if missing:
            if allow_external is True:
                cmd_log(install_extra_repositories(*backend.repositories))
                cmd_log(apt_get_install(*backend.debs))
            else:
                raise RuntimeError(
                    "Unable to retrieve required packages: {}".format(missing))


        if backend.different('juju-gui-source'):
            origin, version_or_branch = parse_source(config['juju-gui-source'])
            if not allow_external and origin == "branch":
                raise RuntimeError(
                    "Unable to fetch requested version of Juju Gui due to " \
                    "allow_external_sources being false in charm config.")

            release_tarball = fetch_gui(
                config['juju-gui-source'], config['command-log-file'])
            setup_gui(release_tarball)

class UpstartMixin(object):
    upstart_scripts = ('haproxy.conf', 'nginx.conf')
    debs = ('curl', 'openssl', 'nginx', 'haproxy')

    def install(self, backend):
        """Set up haproxy and nginx upstart configuration files."""
        backend.log('Setting up haproxy and nginx start up scripts.')
        config = backend.config
        setup_nginx()
        if backend.different('ssl-cert-path', 'ssl-cert-contents', 'ssl-key-contents'):
            save_or_create_certificates(
                config['ssl-cert-path'], config.get('ssl-cert-contents'),
                config.get('ssl-key-contents'))

        source_dir = os.path.join(os.path.dirname(__file__),  '..', 'config')
        for config_file in backend.upstart_scripts:
            shutil.copy(os.path.join(source_dir, config_file), '/etc/init/')

    def start(self, backend):
        with su('root'):
            backend.service_control(NGINX, RESTART)
            backend.service_control(HAPROXY, RESTART)

    def stop(self, backend):
        with su('root'):
            backend.service_control(HAPROXY, STOP)
            backend.service_control(NGINX, STOP)


class GuiMixin(object):
    gui_properties =  set([
        'juju-gui-console-enabled', 'login-help', 'read-only',
        'serve-tests', 'secure'])

    repositories = ('ppa:juju-gui/ppa',)

    def start(self, config):
        if config.different('staging', 'sandbox', *self.gui_properties):
            start_gui(
                config['juju-gui-console-enabled'], config['login-help'],
                config['read-only'], config['staging'], config['ssl-cert-path'],
                config['serve-tests'], secure=config['secure'],
                sandbox=config['sandbox'])
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


class  Backend(object):
    """Compose methods and policy needed to interact
    with a Juju backend. Given a config dict (which typically
    comes from the JSON de-serialization of config.json in JujuGUI).

    """
    def __init__(self, config=None, prev_config=None, **overrides):
        """
        Backends function through composition. __init__ becomes the
        factory method to generate a selection of stragegy classes
        to use together to implement the backend proper."""
        # Ingest the config and build out the ordered list of
        # backend elements to include
        if config is None:
            config = get_config()
        self.config = config
        self.prev_config = prev_config
        self.overrides = overrides

        # We always use upstart.
        backends = [InstallMixin, UpstartMixin]

        api = legacy_juju() and "python" or "go"
        sandbox = config.get('sandbox', False)
        staging = config.get('staging', False)

        if api == 'python':
            if staging:
                if sandbox:
                    backends.append(SandboxBackend)
                else:
                    backends.append(ImprovBackend)
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

        # All backends can manage the gui.
        backends.append(GuiMixin)

        # record our choice mapping classes to instances
        for i, b in enumerate(backends):
            if callable(b):
                backends[i] = b()
        self.backends = backends

    def __getitem__(self, key):
        try:
            return self.config[key]
        except KeyError:
            print("Unable to extract config key '%s' from %s" % (key, self.config))
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

