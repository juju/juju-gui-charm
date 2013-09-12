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

"""Juju GUI charm utilities."""

__all__ = [
    'APACHE_SITE',
    'APACHE_PORTS',
    'API_PORT',
    'CURRENT_DIR',
    'JUJU_AGENT_DIR',
    'JUJU_GUI_DIR',
    'JUJU_PEM',
    'WEB_PORT',
    'cmd_log',
    'compute_build_dir',
    'fetch_api',
    'fetch_gui_from_branch',
    'fetch_gui_release',
    'find_missing_packages',
    'first_path_in_dir',
    'get_api_address',
    'get_npm_cache_archive_url',
    'get_release_file_url',
    'get_zookeeper_address',
    'legacy_juju',
    'log_hook',
    'parse_source',
    'prime_npm_cache',
    'remove_apache_setup',
    'remove_haproxy_setup',
    'render_to_file',
    'save_or_create_certificates',
    'setup_apache_config',
    'setup_gui',
    'setup_haproxy_config',
    'start_agent',
    'start_builtin_server',
    'start_haproxy_apache',
    'start_improv',
    'stop_agent',
    'stop_builtin_server',
    'stop_haproxy_apache',
    'stop_improv',
    'write_gui_config',
]

from contextlib import contextmanager
import errno
import json
import os
import logging
import re
import shutil
from subprocess import CalledProcessError
import tempfile
from urlparse import urlparse

import apt
import tempita

from launchpadlib.launchpad import Launchpad
from shelltoolbox import (
    Serializer,
    apt_get_install,
    command,
    environ,
    run,
    script_name,
    search_file,
    su,
)
from charmhelpers import (
    RESTART,
    START,
    STOP,
    get_config,
    log,
    service_control,
    unit_get,
)


AGENT = 'juju-api-agent'
APACHE = 'apache2'
BUILTIN_SERVER = 'guiserver'
HAPROXY = 'haproxy'
IMPROV = 'juju-api-improv'

API_PORT = 8080
WEB_PORT = 8000

BASE_DIR = '/var/lib/juju-gui'
CURRENT_DIR = os.getcwd()
CONFIG_DIR = os.path.join(CURRENT_DIR, 'config')
JUJU_AGENT_DIR = os.path.join(BASE_DIR, 'juju')
JUJU_GUI_DIR = os.path.join(BASE_DIR, 'juju-gui')
# Builtin server dependencies. The order of these requirements is important.
SERVER_DEPENDENCIES = (
    'futures-2.1.4.tar.gz',
    'tornado-3.1.tar.gz',
    'jujuclient-0.0.9.tar.gz',
    'juju-deployer-0.2.2.tar.gz',
)
SERVER_DIR = os.path.join(CURRENT_DIR, 'server')

APACHE_CFG_DIR = os.path.join(os.path.sep, 'etc', 'apache2')
APACHE_PORTS = os.path.join(APACHE_CFG_DIR, 'ports.conf')
APACHE_SITE = os.path.join(APACHE_CFG_DIR, 'sites-available', 'juju-gui')
HAPROXY_CFG_PATH = os.path.join(os.path.sep, 'etc', 'haproxy', 'haproxy.cfg')

SYS_INIT_DIR = os.path.join(os.path.sep, 'etc', 'init')
AGENT_INIT_PATH = os.path.join(SYS_INIT_DIR, 'juju-api-agent.conf')
GUISERVER_INIT_PATH = os.path.join(SYS_INIT_DIR, 'guiserver.conf')
HAPROXY_INIT_PATH = os.path.join(SYS_INIT_DIR, 'haproxy.conf')
IMPROV_INIT_PATH = os.path.join(SYS_INIT_DIR, 'juju-api-improv.conf')

JUJU_PEM = 'juju.includes-private-key.pem'
DEB_BUILD_DEPENDENCIES = (
    'bzr', 'g++', 'imagemagick', 'make',  'nodejs', 'npm',
)


# Store the configuration from on invocation to the next.
config_json = Serializer(os.path.join(os.path.sep, 'tmp', 'config.json'))
# Bazaar checkout command.
bzr_checkout = command('bzr', 'co', '--lightweight')
# Whether or not the charm is deployed using juju-core.
# If juju-core has been used to deploy the charm, an agent.conf file must
# be present in the charm parent directory.
legacy_juju = lambda: not os.path.exists(
    os.path.join(CURRENT_DIR, '..', 'agent.conf'))

bzr_url_expression = re.compile(r"""
    ^  # Beginning of line.
    ((?:lp:|http:\/\/)[^:]+)  # Branch URL (scheme + domain/path).
    (?::(\d+))?  # Optional branch revision.
    $  # End of line.
""", re.VERBOSE)

results_log = None


def _get_build_dependencies():
    """Install deb dependencies for building."""
    log('Installing build dependencies.')
    cmd_log(apt_get_install(*DEB_BUILD_DEPENDENCIES))


def get_api_address(unit_dir=None):
    """Return the Juju API address.

    If not present in the hook context as an environment variable, try to
    retrieve the address parsing the machiner agent.conf file.
    """
    api_addresses = os.getenv('JUJU_API_ADDRESSES')
    if api_addresses is not None:
        return api_addresses.split()[0]
    # The JUJU_API_ADDRESSES environment variable is not included in the hooks
    # context in older releases of juju-core.  Retrieve it from the machiner
    # agent file instead.
    import yaml  # python-yaml is only installed if juju-core is used.
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


def first_path_in_dir(directory):
    """Return the full path of the first file/dir in *directory*."""
    return os.path.join(directory, os.listdir(directory)[0])


def _get_by_attr(collection, attr, value):
    """Return the first item in collection having attr == value.

    Return None if the item is not found.
    """
    for item in collection:
        if getattr(item, attr) == value:
            return item


def get_release_file_url(project, series_name, release_version):
    """Return the URL of the release file hosted in Launchpad.

    The returned URL points to a release file for the given project, series
    name and release version.
    The argument *project* is a project object as returned by launchpadlib.
    The arguments *series_name* and *release_version* are strings. If
    *release_version* is None, the URL of the latest release will be returned.
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
            if str(file_).endswith('.tgz'):
                return file_.file_link
    raise ValueError('%r: file not found' % release_version)


def get_zookeeper_address(agent_file_path):
    """Retrieve the Zookeeper address contained in the given *agent_file_path*.

    The *agent_file_path* is a path to a file containing a line similar to the
    following::

        env JUJU_ZOOKEEPER="address"
    """
    line = search_file('JUJU_ZOOKEEPER', agent_file_path).strip()
    return line.split('=')[1].strip('"')


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


def parse_source(source):
    """Parse the ``juju-gui-source`` option.

    Return a tuple of two elements representing info on how to deploy Juju GUI.
    Examples:
       - ('stable', None): latest stable release;
       - ('stable', '0.1.0'): stable release v0.1.0;
       - ('trunk', None): latest trunk release;
       - ('trunk', '0.1.0+build.1'): trunk release v0.1.0 bzr revision 1;
       - ('branch', ('lp:juju-gui', 42): release is made from a branch -
         in this case the second element includes the branch URL and revision;
       - ('branch', ('lp:juju-gui', None): no revision is specified;
       - ('url', 'http://example.com/gui'): release from a downloaded file.
    """
    if source.startswith('url:'):
        source = source[4:]
        # Support file paths, including relative paths.
        if urlparse(source).scheme == '':
            if not source.startswith('/'):
                source = os.path.join(os.path.abspath(CURRENT_DIR), source)
            source = "file://%s" % source
        return 'url', source
    if source in ('stable', 'trunk'):
        return source, None
    match = bzr_url_expression.match(source)
    if match is not None:
        return 'branch', match.groups()
    if 'build' in source:
        return 'trunk', source
    return 'stable', source


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


def start_improv(staging_env, ssl_cert_path):
    """Start a simulated juju environment using ``improv.py``."""
    log('Setting up the staging Upstart script.')
    context = {
        'juju_dir': JUJU_AGENT_DIR,
        'keys': ssl_cert_path,
        'port': API_PORT,
        'staging_env': staging_env,
    }
    render_to_file('juju-api-improv.conf.template', context, IMPROV_INIT_PATH)
    log('Starting the staging backend.')
    with su('root'):
        service_control(IMPROV, START)


def stop_improv():
    """Stop a simulated Juju environment."""
    log('Stopping the staging backend.')
    with su('root'):
        service_control(IMPROV, STOP)
    log('Removing the staging Upstart script.')
    cmd_log(run('rm', '-f', IMPROV_INIT_PATH))


def start_agent(ssl_cert_path, read_only=False):
    """Start the Juju agent and connect to the current environment."""
    # Retrieve the Zookeeper address from the start up script.
    unit_name = os.path.basename(
        os.path.realpath(os.path.join(CURRENT_DIR, '..')))
    agent_file = os.path.join(SYS_INIT_DIR, 'juju-{}.conf'.format(unit_name))
    zookeeper = get_zookeeper_address(agent_file)
    log('Setting up the API agent Upstart script.')
    context = {
        'juju_dir': JUJU_AGENT_DIR,
        'keys': ssl_cert_path,
        'port': API_PORT,
        'zookeeper': zookeeper,
        'read_only': read_only
    }
    render_to_file('juju-api-agent.conf.template', context, AGENT_INIT_PATH)
    log('Starting the API agent.')
    with su('root'):
        service_control(AGENT, START)


def stop_agent():
    """Stop the Juju agent."""
    log('Stopping the API agent.')
    with su('root'):
        service_control(AGENT, STOP)
    log('Removing the API agent Upstart script.')
    cmd_log(run('rm', '-f', AGENT_INIT_PATH))


def compute_build_dir(juju_gui_debug, serve_tests):
    """Compute the build directory."""
    with su('root'):
        run('chown', '-R', 'ubuntu:', JUJU_GUI_DIR)
        # XXX 2013-02-05 frankban bug=1116320:
        # External insecure resources are still loaded when testing in the
        # debug environment. For now, switch to the production environment if
        # the charm is configured to serve tests.
    if juju_gui_debug and not serve_tests:
        build_dirname = 'build-debug'
    else:
        build_dirname = 'build-prod'
    return os.path.join(JUJU_GUI_DIR, build_dirname)


def write_gui_config(
        console_enabled, login_help, readonly, in_staging, charmworld_url,
        build_dir, secure=True, sandbox=False, use_analytics=False,
        default_viewmode='sidebar', show_get_juju_button=False,
        config_js_path=None):
    """Generate the GUI configuration file."""
    log('Generating the Juju GUI configuration file.')
    is_legacy_juju = legacy_juju()
    user, password = None, None
    if (is_legacy_juju and in_staging) or sandbox:
        user, password = 'admin', 'admin'
    else:
        user, password = None, None
    api_backend = 'python' if is_legacy_juju else 'go'
    if secure:
        protocol = 'wss'
    else:
        log('Running in insecure mode! Port 80 will serve unencrypted.')
        protocol = 'ws'
    context = {
        'raw_protocol': protocol,
        'address': unit_get('public-address'),
        'console_enabled': json.dumps(console_enabled),
        'login_help': json.dumps(login_help),
        'password': json.dumps(password),
        'api_backend': json.dumps(api_backend),
        'readonly': json.dumps(readonly),
        'user': json.dumps(user),
        'protocol': json.dumps(protocol),
        'sandbox': json.dumps(sandbox),
        'charmworld_url': json.dumps(charmworld_url),
        'use_analytics': json.dumps(use_analytics),
        'default_viewmode': json.dumps(default_viewmode),
        'show_get_juju_button': json.dumps(show_get_juju_button),
    }
    if config_js_path is None:
        config_js_path = os.path.join(
            build_dir, 'juju-ui', 'assets', 'config.js')
    render_to_file('config.js.template', context, config_js_path)


def setup_haproxy_config(ssl_cert_path, secure=True):
    """Generate the haproxy configuration file."""
    log('Setting up haproxy Upstart file.')
    config_path = os.path.join(CONFIG_DIR, 'haproxy.conf')
    shutil.copy(config_path, SYS_INIT_DIR)
    log('Generating haproxy configuration file.')
    is_legacy_juju = legacy_juju()
    if is_legacy_juju:
        # The PyJuju API agent is listening on localhost.
        api_address = '127.0.0.1:{}'.format(API_PORT)
    else:
        # Retrieve the juju-core API server address.
        api_address = get_api_address()
    context = {
        'api_address': api_address,
        'api_pem': JUJU_PEM,
        'legacy_juju': is_legacy_juju,
        'ssl_cert_path': ssl_cert_path,
        # In PyJuju environments, use the same certificate for both HTTPS and
        # WebSocket connections. In juju-core the system already has the proper
        # certificate installed.
        'web_pem': JUJU_PEM,
        'web_port': WEB_PORT,
        'secure': secure
    }
    render_to_file('haproxy.cfg.template', context, HAPROXY_CFG_PATH)


def remove_haproxy_setup():
    """Remove haproxy setup."""
    log('Removing haproxy setup.')
    cmd_log(run('rm', '-f', HAPROXY_CFG_PATH))
    cmd_log(run('rm', '-f', HAPROXY_INIT_PATH))


def setup_apache_config(build_dir, serve_tests=False):
    """Set up the Apache configuration."""
    log('Generating the Apache site configuration files.')
    tests_root = os.path.join(JUJU_GUI_DIR, 'test', '') if serve_tests else ''
    context = {
        'port': WEB_PORT,
        'server_root': build_dir,
        'tests_root': tests_root,
    }
    render_to_file('apache-ports.template', context, APACHE_PORTS)
    cmd_log(run('chown', 'ubuntu:', APACHE_PORTS))
    render_to_file('apache-site.template', context, APACHE_SITE)
    cmd_log(run('chown', 'ubuntu:', APACHE_SITE))
    with su('root'):
        run('a2dissite', 'default')
        run('a2ensite', 'juju-gui')
        run('a2enmod', 'headers')


def remove_apache_setup():
    """Remove Apache setup."""
    if os.path.exists(APACHE_SITE):
        log('Removing Apache setup.')
        cmd_log(run('rm', '-f', APACHE_SITE))
        with su('root'):
            run('a2dismod', 'headers')
            run('a2dissite', 'juju-gui')
            run('a2ensite', 'default')
        if os.path.exists(APACHE_PORTS):
            cmd_log(run('rm', '-f', APACHE_PORTS))


def start_haproxy_apache(
        build_dir, serve_tests, ssl_cert_path, secure):
    """Set up and start the haproxy and Apache services."""
    log('Setting up Apache and haproxy.')
    setup_apache_config(build_dir, serve_tests)
    setup_haproxy_config(ssl_cert_path, secure)
    log('Starting the haproxy and Apache services.')
    with su('root'):
        service_control(APACHE, RESTART)
        service_control(HAPROXY, RESTART)


def stop_haproxy_apache():
    """Stop the haproxy and Apache services."""
    log('Stopping the haproxy and Apache services.')
    with su('root'):
        service_control(HAPROXY, STOP)
        service_control(APACHE, STOP)
    remove_haproxy_setup()
    remove_apache_setup()


def install_builtin_server():
    """Install the builtin server code."""
    log('Installing the builtin server dependencies.')
    for dependency_name in SERVER_DEPENDENCIES:
        dependency = os.path.join(CURRENT_DIR, 'deps', dependency_name)
        with su('root'):
            cmd_log(run('pip', 'install', dependency))
    log('Installing the builtin server.')
    setup_cmd = os.path.join(SERVER_DIR, 'setup.py')
    with su('root'):
        cmd_log(run('/usr/bin/python', setup_cmd, 'install'))


def write_builtin_server_startup(
        gui_root, ssl_cert_path, serve_tests=False, sandbox=False,
        builtin_server_logging='info', insecure=False):
    """Generate the builtin server Upstart file."""
    log('Generating the builtin server Upstart file.')
    context = {
        'builtin_server_logging': builtin_server_logging,
        'gui_root': gui_root,
        'insecure': insecure,
        'sandbox': sandbox,
        'serve_tests': serve_tests,
        'ssl_cert_path': ssl_cert_path,
    }
    if not sandbox:
        is_legacy_juju = legacy_juju()
        if is_legacy_juju:
            api_url = 'wss://127.0.0.1:{}/ws'.format(API_PORT)
        else:
            api_url = 'wss://{}'.format(get_api_address())
        context.update({
            'api_url': api_url,
            'api_version': 'python' if is_legacy_juju else 'go',
        })
    if serve_tests:
        context['tests_root'] = os.path.join(JUJU_GUI_DIR, 'test', '')
    render_to_file(
        'guiserver.conf.template', context, GUISERVER_INIT_PATH)


def start_builtin_server(
        build_dir, ssl_cert_path, serve_tests, sandbox, builtin_server_logging,
        insecure):
    """Start the builtin server."""
    write_builtin_server_startup(
        build_dir, ssl_cert_path, serve_tests=serve_tests, sandbox=sandbox,
        builtin_server_logging=builtin_server_logging, insecure=insecure)
    log('Starting the builtin server.')
    with su('root'):
        service_control(BUILTIN_SERVER, RESTART)


def stop_builtin_server():
    """Stop the builtin server."""
    log('Stopping the builtin server.')
    with su('root'):
        service_control(BUILTIN_SERVER, STOP)
    cmd_log(run('rm', '-f', GUISERVER_INIT_PATH))


def get_npm_cache_archive_url(Launchpad=Launchpad):
    """Figure out the URL of the most recent NPM cache archive on Launchpad."""
    launchpad = Launchpad.login_anonymously('Juju GUI charm', 'production')
    project = launchpad.projects['juju-gui']
    # Find the URL of the most recently created NPM cache archive.
    npm_cache_url = get_release_file_url(project, 'npm-cache', None)
    return npm_cache_url


def prime_npm_cache(npm_cache_url):
    """Download NPM cache archive and prime the NPM cache with it."""
    # Download the cache archive and then uncompress it into the NPM cache.
    npm_cache_archive = os.path.join(CURRENT_DIR, 'npm-cache.tgz')
    cmd_log(run('curl', '-L', '-o', npm_cache_archive, npm_cache_url))
    npm_cache_dir = os.path.expanduser('~/.npm')
    # The NPM cache directory probably does not exist, so make it if not.
    try:
        os.mkdir(npm_cache_dir)
    except OSError, e:
        # If the directory already exists then ignore the error.
        if e.errno != errno.EEXIST:  # File exists.
            raise
    uncompress = command('tar', '-x', '-z', '-C', npm_cache_dir, '-f')
    cmd_log(uncompress(npm_cache_archive))


def fetch_gui_from_branch(branch_url, revision, logpath):
    """Retrieve the Juju GUI from a branch and build a release archive."""
    # Make sure we have the needed dependencies.
    _get_build_dependencies()
    # Inject NPM packages into the cache for faster building.
    prime_npm_cache(get_npm_cache_archive_url())
    # Create a release starting from a branch.
    juju_gui_source_dir = os.path.join(CURRENT_DIR, 'juju-gui-source')
    checkout_args, revno = ([], 'latest revno') if revision is None else (
        ['--revision', revision], 'revno {}'.format(revision))
    log('Retrieving Juju GUI source checkout from {} ({}).'.format(
        branch_url, revno))
    cmd_log(run('rm', '-rf', juju_gui_source_dir))
    checkout_args.extend([branch_url, juju_gui_source_dir])
    cmd_log(bzr_checkout(*checkout_args))
    log('Preparing a Juju GUI release.')
    logdir = os.path.dirname(logpath)
    fd, name = tempfile.mkstemp(prefix='make-distfile-', dir=logdir)
    log('Output from "make distfile" sent to %s' % name)
    with environ(NO_BZR='1'):
        run('make', '-C', juju_gui_source_dir, 'distfile',
            stdout=fd, stderr=fd)
    return first_path_in_dir(
        os.path.join(juju_gui_source_dir, 'releases'))


def fetch_gui_release(origin, version):
    """Retrieve a Juju GUI release."""
    log('Retrieving Juju GUI release.')
    if origin == 'url':
        file_url = version
    else:
        # Retrieve a release from Launchpad.
        launchpad = Launchpad.login_anonymously(
            'Juju GUI charm', 'production')
        project = launchpad.projects['juju-gui']
        file_url = get_release_file_url(project, origin, version)
    log('Downloading release file from %s.' % file_url)
    release_tarball = os.path.join(CURRENT_DIR, 'release.tgz')
    cmd_log(run('curl', '-L', '-o', release_tarball, file_url))
    return release_tarball


def fetch_api(juju_api_branch):
    """Retrieve the Juju branch, removing it first if already there."""
    # Retrieve Juju API source checkout.
    log('Retrieving Juju API source checkout.')
    cmd_log(run('rm', '-rf', JUJU_AGENT_DIR))
    cmd_log(bzr_checkout(juju_api_branch, JUJU_AGENT_DIR))


def setup_gui(release_tarball):
    """Set up Juju GUI."""
    # Uncompress the release tarball.
    log('Installing Juju GUI.')
    release_dir = os.path.join(BASE_DIR, 'release')
    cmd_log(run('rm', '-rf', release_dir))
    os.mkdir(release_dir)
    uncompress = command('tar', '-x', '-z', '-C', release_dir, '-f')
    cmd_log(uncompress(release_tarball))
    # Link the Juju GUI dir to the contents of the release tarball.
    cmd_log(run('ln', '-sf', first_path_in_dir(release_dir), JUJU_GUI_DIR))


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
        cmd_log(run(
            'openssl', 'req', '-new', '-newkey', 'rsa:4096',
            '-days', '365', '-nodes', '-x509', '-subj',
            # These are arbitrary test values for the certificate.
            '/C=GB/ST=Juju/L=GUI/O=Ubuntu/CN=juju.ubuntu.com',
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
