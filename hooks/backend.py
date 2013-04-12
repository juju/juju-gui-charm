## These normally depend on python packages being installed
## from hooks/install. If we are unable to use external code
## due to some  deployment restrictions these deps will already
## have been installed or this code will fail.
from charmhelpers import (
    log,
    open_port,
    service_control,
    START,
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
    NGINX,
    cmd_log,
    fetch_api,
    fetch_gui,
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
        cmd_log(install_extra_repositories(backend.repositories))
        cmd_log(apt_get_install(backend.debs))
        if backend.different('juju-gui-source'):
            release_tarball = fetch_gui(
                config['juju-gui-source'], config['command-log-file'])
        setup_gui(release_tarball)
        setup_nginx()
        if backend.different('ssl-cert-path', 'ssl-cert-contents', 'ssl-key-contents'):
            save_or_create_certificates(
                config['ssl-cert-path'], config.get('ssl-cert-contents'),
                config.get('ssl-key-contents'))

class UpstartMixin(object):
    upstart_scripts = ('haproxy.conf', 'nginx.conf')
    dependencies = ('nginx', 'haproxy')
    debs = ('curl', 'openssl')

    def install(self, backend):
        """Set up haproxy and nginx upstart configuration files."""
        log('Setting up haproxy and nginx start up scripts.')
        source_dir = os.path.join(os.path.dirname(__file__),  '..', 'config')
        for config_file in backend.upstart_scripts:
            shutil.copy(os.path.join(source_dir, config_file), '/etc/init/')

    def start(self, backend):
        with su('root'):
            service_control(HAPROXY, START)
            service_control(NGINX, START)

    def stop(self, backend):
        with su('root'):
            service_control(HAPROXY, STOP)
            service_control(NGINX, STOP)


class GuiMixin(object):
    gui_properties =  set([
        'juju-gui-console-enabled', 'login-help', 'read-only',
        'serve-tests', 'secure'])

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
    repositories = ('ppa:juju-gui/ppa',)
    build_dependencies = (
        'bzr', 'imagemagick', 'make', 'nodejs', 'npm')

    def start(self, config):
        start_agent(config['ssl-cert-path'])

    def stop(self, config):
        service_control(AGENT, STOP)

class ImprovBackend(object):
    staging_dependencies = ('zookeeper', )

    def install(self, config):
        if config.different('juju-api-branch'):
            fetch_api(config(['juju-api-branch']))

    def start(self, config):
        start_improv(
            config['staging-environment'], config['ssl-cert-path'])

    def stop(self, config):
        service_control(IMPROV, STOP)

class GoBackend(object):
    debs = ('python-yaml', )




class StopChain(Exception):
    """Stop Processing a chain command without raising
    another error.
    """

def chain(name, reverse=False):
    """Helper method to compose a set of strategy objects into
    a callable.

    Each method is called in the context of its strategy
    instance (normal OOP) and its argument is the Backend
    instance.
    """
    # chain method calls through all implementing mixins
    def method(self):
        workingset = self.backends
        if reverse:
            workingset = reversed(workingset)
        for backend in workingset:
            call = backend.__class__.__dict__.get(name)
            if call:
                try:
                    call(backend, self)
                except StopChain:
                    break


    method.__name__ = name
    return method

def merge(name):
    """Helper to merge a property from a set of strategy objects
    into a unified set.
    """
    # return merged property from every providing backend as a set
    @property
    def method(self):
        result = set()
        for backend in self.backends:
            segment = backend.__class__.__dict__.get(name)
            if segment and isinstance(segment, (list, tuple, set)):
                result |= set(segment)

        return result
    return method


class  Backend(object):
    """Compose methods and policy needed to interact
    with a Juju backend. Given a config dict (which typically
    comes from the JSON de-serialization of config.json in JujuGUI).

    """
    def __init__(self, config, prev_config=None):
        """
        Backends function through composition. __init__ becomes the
        factory method to generate a selection of stragegy classes
        to use together to implement the backend proper."""
        # Ingest the config and build out the ordered list of
        # backend elements to include
        self.config = config
        self.prev_config = prev_config


        # We always use upstart.
        backends = [InstallMixin, UpstartMixin]

        api = config.get('apiBackend', 'python')
        #serve_tests = config.get('serve-tests', False)
        sandbox = config.get('sandbox', False)
        staging = config.get('staging', False)

        if config.get('use_external_code', True) is not False:
            backends.insert(0, InstallMixin)

        if api == 'python':
            backends.append(PythonBackend)
            if staging:
                if sandbox:
                    backends.insert(0, SandboxBackend)
                else:
                    backends.insert(0, ImprovBackend)
        else:
            if staging:
                raise ValueError(
                    "Unable to use staging with {} backend".format(api))
            if sandbox:
                raise ValueError(
                    "Unable to use sandbox with {} backend".format(api))
            backends.append(GoBackend)

        # All backends can manage the gui.
        backends.insert(0, GuiMixin)

        # record our choice mapping classes to instances
        for i, b in enumerate(backends):
            if callable(b):
                backends[i] = b()
        self.backends = backends

    def __getitem__(self, key):
        return self.config[key]

    def different(self, *keys):
        """Return a boolean indicating if the current config
        value differs from the config value passed in prev_config
        with respect to any of the passed in string keys.
        """
        if self.prev_config is None:
            return True

        for key in keys:
            current = self[key]
            prev = self.prev_config.get(key)
            r = current == prev
            if r: return True
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

