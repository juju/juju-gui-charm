# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2012-2014 Canonical Ltd.
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

"""Juju GUI charm utilities."""

from contextlib import contextmanager
from distutils.version import LooseVersion
import os
import logging
import re
import shutil
from subprocess import CalledProcessError
import time
import urlparse
import yaml

import apt
import tempita

from charmhelpers import (
    close_port,
    get_config,
    log,
    open_port,
    RESTART,
    service_control,
    STOP
)
from shelltoolbox import (
    apt_get_install,
    install_extra_repositories,
    run,
    script_name,
    Serializer,
    su,
)


__all__ = [
    'CURRENT_DIR',
    'JUJU_GUI_DIR',
    'JUJU_PEM',
    'cmd_log',
    'find_missing_packages',
    'get_api_address',
    'get_launchpad_release',
    'get_port',
    'get_release_file_path',
    'install_missing_packages',
    'log_hook',
    'render_to_file',
    'save_or_create_certificates',
    'setup_gui',
    'setup_ports',
    'start_builtin_server',
    'stop_builtin_server',
]


GUISERVER = 'guiserver'

BASE_DIR = '/var/lib/juju-gui'
CURRENT_DIR = os.getcwd()
CONFIG_DIR = os.path.join(CURRENT_DIR, 'config')
JUJU_GUI_DIR = os.path.join(BASE_DIR, 'juju-gui')
RELEASES_DIR = os.path.join(CURRENT_DIR, 'releases')
SERVER_DIR = os.path.join(CURRENT_DIR, 'server')

# Support both upstart via conf file in /etc/init
# and systemd via service file in /lib/systemd/system
# Each of these execs /usr/local/bin/runserver.sh which is updated
# on charm config changes.
SYS_INIT_DIR = os.path.join(os.path.sep, 'etc', 'init')
GUISERVER_INIT_PATH = os.path.join(SYS_INIT_DIR, 'guiserver.conf')
SYSTEMD_SERVICE_DIR = os.path.join(os.path.sep, 'lib', 'systemd', 'system')
GUISERVER_SERVICE_PATH = os.path.join(SYSTEMD_SERVICE_DIR, 'guiserver.service')
RUNSERVER_DIR = os.path.join(os.path.sep, 'usr', 'local', 'bin')
RUNSERVER_SH_PATH = os.path.join(RUNSERVER_DIR, 'runserver.sh')

JUJU_PEM = 'juju.includes-private-key.pem'


# Store the configuration from one invocation to the next.
config_json = Serializer(os.path.join(os.path.sep, 'tmp', 'config.json'))
release_expression = re.compile(r"""
    juju-?gui-  # Juju GUI prefix.
    (
        \d+\.\d+\.\d+  # Major, minor, and patch version numbers.
        (?:\+build\.\w+)?  # Optional git hash for development releases.
    )
    \.(?:tar.bz2|tgz|xz)  # File extension.
""", re.VERBOSE)
results_log = None


def get_api_address(unit_dir=None):
    """Return the Juju API address.

    """
    api_addresses = os.getenv('JUJU_API_ADDRESSES')
    if api_addresses is not None:
        return api_addresses.split()[0]
    # The JUJU_API_ADDRESSES environment variable is not included in the hooks
    # context in older releases of juju-core.  Retrieve it from the machiner
    # agent file instead.
    if unit_dir is None:
        base_dir = os.path.join(CURRENT_DIR, '..', '..')
    else:
        base_dir = os.path.join(unit_dir, '..')
    base_dir = os.path.abspath(base_dir)
    for dirname in os.listdir(base_dir):
        if dirname.startswith('machine-'):
            agent_conf = os.path.join(base_dir, dirname, 'agent.conf')
            break
    else:
        raise IOError('Juju agent configuration file not found.')
    contents = yaml.load(open(agent_conf))
    return contents['apiinfo']['addrs'][0]
    return api_addresses.split()[0]


def _get_by_attr(collection, attr, value):
    """Return the first item in collection having attr == value.

    Return None if the item is not found.
    """
    for item in collection:
        if getattr(item, attr) == value:
            return item


def get_launchpad_release(project, series_name, release_version):
    """Return the URL and the name of the release file hosted in Launchpad.

    The returned URL points to a release file for the given project, series
    name and release version.
    The argument *project* is a project object as returned by launchpadlib.
    The arguments *series_name* and *release_version* are strings. If
    *release_version* is None, the URL and file name of the latest release will
    be returned.
    """
    series = _get_by_attr(project.series, 'name', series_name)
    if series is None:
        raise ValueError('%r: series not found' % series_name)
    # Releases are returned by Launchpad in reverse date order.
    releases = list(series.releases)
    if not releases:
        raise ValueError('%r: series does not contain releases' % series_name)
    if release_version is not None:
        release = _get_by_attr(releases, 'version', release_version)
        if release is None:
            raise ValueError('%r: release not found' % release_version)
        releases = [release]
    for release in releases:
        for file_ in release.files:
            file_url = str(file_)
            if file_url.endswith('.tgz') or file_url.endswith('.xz'):
                filename = os.path.split(urlparse.urlsplit(file_url).path)[1]
                return file_.file_link, filename
    raise ValueError('%r: file not found' % release_version)


@contextmanager
def log_hook():
    """Log when a hook starts and stops its execution.

    Also log to stdout possible CalledProcessError exceptions raised executing
    the hook.
    """
    script = script_name()
    log(">>> Entering {}".format(script))
    try:
        yield
    except CalledProcessError as err:
        log('Exception caught:')
        log(err.output)
        raise
    finally:
        log("<<< Exiting {}".format(script))


def render_to_file(template_name, context, destination):
    """Render the given *template_name* into *destination* using *context*.

    The tempita template language is used to render contents
    (see http://pythonpaste.org/tempita/).
    The argument *template_name* is the name or path of the template file:
    it may be either a path relative to ``../config`` or an absolute path.
    The argument *destination* is a file path.
    The argument *context* is a dict-like object.
    """
    template_path = os.path.join(CONFIG_DIR, template_name)
    template = tempita.Template.from_filename(template_path)
    with open(destination, 'w') as stream:
        stream.write(template.substitute(context))


def _setupLogging():
    global results_log
    if results_log is not None:
        return

    # Make sure that the root logger isn't configured already. If it does,
    # this basicConfig will be a noop and not setup the expected file handler
    # on the logger.
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    config = get_config()
    logging.basicConfig(
        filename=config['command-log-file'],
        level=logging.INFO,
        format="%(asctime)s: %(name)s@%(levelname)s %(message)s")
    results_log = logging.getLogger('juju-gui')


def cmd_log(results):
    global results_log
    if not results:
        return
    if results_log is None:
        _setupLogging()
    # Since 'results' may be multi-line output, start it on a separate line
    # from the logger timestamp, etc.
    results_log.info('\n' + results)


# Simple checker function for port ranges.
port_in_range = lambda port: 1 <= port <= 65535


def setup_ports(previous_port, current_port):
    """Open or close ports based on the supplied ports.

    The given ports specify the previously provided and the current value.
    They can be int numbers if the ports are specified, None otherwise, in
    which case the default ones (80 and 443) are used.
    """
    # If a custom port was previously defined we want to make sure we close it.
    if previous_port is not None and port_in_range(previous_port):
        log('Closing user provided port {}.'.format(previous_port))
        close_port(previous_port)
    if current_port is not None:
        if port_in_range(current_port):
            # Ensure the default ports are closed when setting the custom one.
            log('Closing default ports 80 and 443.')
            close_port(80)
            close_port(443)
            # Open the custom defined port.
            log('Opening user provided port {}.'.format(current_port))
            open_port(current_port)
            return
        log('Ignoring provided port {}: not in range.'.format(current_port))
    log('Opening default ports 80 and 443.')
    open_port(80)
    open_port(443)


def get_port():
    """Return the current port the GUI server is listening to."""
    config = get_config()
    default_port = 443 if config['secure'] else 80
    return config.get('port', default_port) or default_port


def install_builtin_server():
    """Install the builtin server code."""
    log('Installing the builtin server dependencies.')
    deps = os.path.join(CURRENT_DIR, 'deps')
    requirements = os.path.join(CURRENT_DIR, 'server-requirements.pip')
    # Install the builtin server dependencies avoiding to download requirements
    # from the network.
    with su('root'):
        cmd_log(run(
            '/usr/bin/pip2', 'install', '--no-index', '--no-dependencies',
            '--find-links', 'file:///{}'.format(deps),
            '-r', requirements
        ))
    log('Installing the builtin server.')
    setup_cmd = os.path.join(SERVER_DIR, 'setup.py')
    with su('root'):
        cmd_log(run('/usr/bin/python', setup_cmd, 'install'))


# TODO: add these config options -- some may no longer be necessary, some may
# need updates to the gui
# * charmstore url
# * console enabled (?)
# * cached fonts (?)
# * read only (?)
# * test serving (?)
# * remove charmworld (?)
def write_builtin_server_startup(
        ssl_cert_path, serve_tests=False, sandbox=False,
        builtin_server_logging='info', insecure=False, charmworld_url='',
        env_password=None, env_uuid=None, juju_version=None, debug=False,
        port=None, jem_location=None, interactive_login=False, gzip=True,
        gtm_enabled=False):
    """Generate the builtin server Upstart file."""
    log('Generating the builtin server Upstart file.')
    context = {
        'builtin_server_logging': builtin_server_logging,
        'charmworld_url': charmworld_url,
        'env_password': env_password,
        'env_uuid': env_uuid,
        'gtm_enabled': gtm_enabled,
        'gzip': gzip,
        'http_proxy': os.environ.get('http_proxy'),
        'https_proxy': os.environ.get('https_proxy'),
        'insecure': insecure,
        'interactive_login': interactive_login,
        'jem_location': jem_location,
        'juju_gui_debug': debug,
        'juju_version': juju_version,
        'no_proxy': os.environ.get('no_proxy', os.environ.get('NO_PROXY')),
        'port': port,
        'sandbox': sandbox,
        'serve_tests': serve_tests,
        'ssl_cert_path': ssl_cert_path,
    }
    if not sandbox:
        api_url = 'wss://{}'.format(get_api_address())
        context.update({
            'api_url': api_url,
            'api_version': 'go',
        })
    if serve_tests:
        context['tests_root'] = os.path.join(JUJU_GUI_DIR, 'test', '')
    render_to_file(
        'guiserver.conf.template', context, GUISERVER_INIT_PATH)
    render_to_file(
        'guiserver.service.template', context, GUISERVER_SERVICE_PATH)
    render_to_file(
        'runserver.sh.template', context, RUNSERVER_SH_PATH)
    os.chmod(RUNSERVER_SH_PATH, 0755)


def start_builtin_server(
        ssl_cert_path, serve_tests, sandbox, builtin_server_logging,
        insecure, charmworld_url, env_password=None, env_uuid=None,
        juju_version=None, debug=False, port=None, jem_location=None,
        interactive_login=False, gzip=True, gtm_enabled=False):
    """Start the builtin server."""
    if (port is not None) and not port_in_range(port):
        # Do not use the user provided port if it is not valid.
        port = None
    write_builtin_server_startup(
        ssl_cert_path, serve_tests=serve_tests, sandbox=sandbox,
        builtin_server_logging=builtin_server_logging, insecure=insecure,
        charmworld_url=charmworld_url, env_password=env_password,
        env_uuid=env_uuid, juju_version=juju_version,
        debug=debug, port=port, jem_location=jem_location,
        interactive_login=interactive_login, gzip=gzip,
        gtm_enabled=gtm_enabled)
    log('Starting the builtin server.')
    with su('root'):
        service_control(GUISERVER, RESTART)


def stop_builtin_server():
    """Stop the builtin server."""
    log('Stopping the builtin server.')
    with su('root'):
        service_control(GUISERVER, STOP)
    cmd_log(run('rm', '-f', GUISERVER_INIT_PATH))


def get_release_file_path(version=None):
    """Return the local path of the release file with the given version.

    If version is None, return the path of the last release.
    Raise a ValueError if no releases are found in the local repository.
    """
    version_path_map = {}
    # Collect the locally stored releases.
    for filename in os.listdir(RELEASES_DIR):
        match = release_expression.match(filename)
        if match is not None:
            release_version = match.groups()[0]
            release_path = os.path.join(RELEASES_DIR, filename)
            version_path_map[release_version] = release_path
    # We expect the charm to include at least one release file.
    if not version_path_map:
        raise ValueError('Error: no releases found in the charm.')
    if version is None:
        # Return the path of the last release.
        last_version = sorted(version_path_map.keys(), key=LooseVersion)[-1]
        return version_path_map[last_version]
    # Return the path of the release with the requested version, or None if
    # the release is not found.
    return version_path_map.get(version)


def setup_gui():
    """Set up Juju GUI."""

    # Install ensuring network access is not used.  All dependencies should
    # already be installed from the deps directory.
    jujugui_deps = os.path.join(CURRENT_DIR, 'jujugui-deps')
    release_tarball_path = get_release_file_path()
    log('Installing Juju GUI from {}.'.format(release_tarball_path))
    cmd = (
        '/usr/bin/pip2',  'install', '--no-index',
        '--find-links', 'file:///{}'.format(jujugui_deps),
        release_tarball_path,
    )
    with su('root'):
        cmd_log(run(*cmd))


def save_or_create_certificates(
        ssl_cert_path, ssl_cert_contents, ssl_key_contents):
    """Generate the SSL certificates.

    If both *ssl_cert_contents* and *ssl_key_contents* are provided, use them
    as certificates; otherwise, generate them.

    Also create a pem file, suitable for use in the haproxy configuration,
    concatenating the key and the certificate files.
    """
    crt_path = os.path.join(ssl_cert_path, 'juju.crt')
    key_path = os.path.join(ssl_cert_path, 'juju.key')
    if not os.path.exists(ssl_cert_path):
        os.makedirs(ssl_cert_path)
    if ssl_cert_contents and ssl_key_contents:
        # Save the provided certificates.
        with open(crt_path, 'w') as cert_file:
            cert_file.write(ssl_cert_contents)
        with open(key_path, 'w') as key_file:
            key_file.write(ssl_key_contents)
    else:
        # Generate certificates.
        # See http://superuser.com/questions/226192/openssl-without-prompt
        cn = 'your-jujugui-{0}.local'.format(int(time.time()))
        cmd_log(run(
            'openssl', 'req', '-new', '-newkey', 'rsa:4096',
            '-days', '365', '-nodes', '-x509', '-subj',
            # These are arbitrary test values for the certificate.
            '/C=GB/ST=Juju/L=GUI/O=Ubuntu/CN={0}'.format(cn),
            '-keyout', key_path, '-out', crt_path))
    # Generate the pem file.
    pem_path = os.path.join(ssl_cert_path, JUJU_PEM)
    if os.path.exists(pem_path):
        os.remove(pem_path)
    with open(pem_path, 'w') as pem_file:
        shutil.copyfileobj(open(key_path), pem_file)
        shutil.copyfileobj(open(crt_path), pem_file)


def find_missing_packages(*packages):
    """Given a list of packages, return the packages which are not installed.
    """
    cache = apt.Cache()
    missing = set()
    for pkg_name in packages:
        try:
            pkg = cache[pkg_name]
        except KeyError:
            missing.add(pkg_name)
            continue
        if pkg.is_installed:
            continue
        missing.add(pkg_name)
    return missing


def install_missing_packages(packages, repository=None):
    """Install the required debian packages if they are missing.

    If repository is not None, add the given apt repository before installing
    the dependencies.
    """
    missing = find_missing_packages(*packages)
    if missing:
        if repository is not None:
            log('Adding the apt repository {}.'.format(repository))
            install_extra_repositories(repository)
        log('Installing deb packages: {}.'.format(', '.join(missing)))
        cmd_log(apt_get_install(*missing))
    else:
        log('No missing deb packages.')
