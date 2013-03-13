"""Juju GUI charm utilities."""

__all__ = [
    'AGENT',
    'API_PORT',
    'bzr_checkout',
    'cmd_log',
    'CURRENT_DIR',
    'fetch_api',
    'fetch_gui',
    'first_path_in_dir',
    'get_release_file_url',
    'get_staging_dependencies',
    'get_zookeeper_address',
    'HAPROXY',
    'IMPROV',
    'JUJU_DIR',
    'JUJU_GUI_DIR',
    'JUJU_GUI_SITE',
    'JUJU_PEM',
    'log_hook',
    'NGINX',
    'parse_source',
    'render_to_file',
    'save_or_create_certificates',
    'setup_gui',
    'setup_nginx',
    'start_agent',
    'start_gui',
    'start_improv',
    'stop',
    'WEB_PORT',
]

from contextlib import contextmanager
import json
import os
import logging
import shutil
from subprocess import CalledProcessError
import tempfile
import tempita

from launchpadlib.launchpad import Launchpad
from shelltoolbox import (
    apt_get_install,
    command,
    environ,
    install_extra_repositories,
    run,
    script_name,
    search_file,
    Serializer,
    su,
)
from charmhelpers import (
    get_config,
    log,
    service_control,
    START,
    STOP,
    unit_get,
)


AGENT = 'juju-api-agent'
IMPROV = 'juju-api-improv'
HAPROXY = 'haproxy'
NGINX = 'nginx'

API_PORT = 8080
WEB_PORT = 8000

CURRENT_DIR = os.getcwd()
JUJU_DIR = os.path.join(CURRENT_DIR, 'juju')
JUJU_GUI_DIR = os.path.join(CURRENT_DIR, 'juju-gui')
JUJU_GUI_SITE = '/etc/nginx/sites-available/juju-gui'
JUJU_PEM = 'juju.includes-private-key.pem'
BUILD_REPOSITORIES = ('ppa:chris-lea/node.js',)
DEB_BUILD_DEPENDENCIES = (
    'bzr', 'imagemagick', 'make',  'nodejs', 'npm',
)
DEB_STAGE_DEPENDENCIES = (
    'zookeeper',
)


# Store the configuration from on invocation to the next.
config_json = Serializer('/tmp/config.json')
# Bazaar checkout command.
bzr_checkout = command('bzr', 'co', '--lightweight')


def _get_build_dependencies():
    """Install deb dependencies for building."""
    log('Installing build dependencies.')
    cmd_log(install_extra_repositories(*BUILD_REPOSITORIES))
    cmd_log(apt_get_install(*DEB_BUILD_DEPENDENCIES))


def get_staging_dependencies():
    """Install deb dependencies for the stage (improv) environment."""
    log('Installing stage dependencies.')
    cmd_log(apt_get_install(*DEB_STAGE_DEPENDENCIES))


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
    """Log when an hook starts and stops its execution.

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
       - ('branch', 'lp:juju-gui'): release is made from a branch.
    """
    if source in ('stable', 'trunk'):
        return source, None
    if source.startswith('lp:') or source.startswith('http://'):
        return 'branch', source
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
    template_path = os.path.join(
        os.path.dirname(__file__), '..', 'config', template_name)
    template = tempita.Template.from_filename(template_path)
    with open(destination, 'w') as stream:
        stream.write(template.substitute(context))


results_log = None


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


def start_improv(staging_env, ssl_cert_path,
                 config_path='/etc/init/juju-api-improv.conf'):
    """Start a simulated juju environment using ``improv.py``."""
    log('Setting up staging start up script.')
    context = {
        'juju_dir': JUJU_DIR,
        'keys': ssl_cert_path,
        'port': API_PORT,
        'staging_env': staging_env,
    }
    render_to_file('juju-api-improv.conf.template', context, config_path)
    log('Starting the staging backend.')
    with su('root'):
        service_control(IMPROV, START)


def start_agent(ssl_cert_path, config_path='/etc/init/juju-api-agent.conf'):
    """Start the Juju agent and connect to the current environment."""
    # Retrieve the Zookeeper address from the start up script.
    unit_dir = os.path.realpath(os.path.join(CURRENT_DIR, '..'))
    agent_file = '/etc/init/juju-{0}.conf'.format(os.path.basename(unit_dir))
    zookeeper = get_zookeeper_address(agent_file)
    log('Setting up API agent start up script.')
    context = {
        'juju_dir': JUJU_DIR,
        'keys': ssl_cert_path,
        'port': API_PORT,
        'zookeeper': zookeeper,
    }
    render_to_file('juju-api-agent.conf.template', context, config_path)
    log('Starting API agent.')
    with su('root'):
        service_control(AGENT, START)


def start_gui(
        console_enabled, login_help, readonly, in_staging, ssl_cert_path,
        serve_tests, haproxy_path='/etc/haproxy/haproxy.cfg',
        nginx_path=JUJU_GUI_SITE, config_js_path=None, secure=True):
    """Set up and start the Juju GUI server."""
    with su('root'):
        run('chown', '-R', 'ubuntu:', JUJU_GUI_DIR)
    # XXX 2013-02-05 frankban bug=1116320:
        # External insecure resources are still loaded when testing in the
        # debug environment. For now, switch to the production environment if
        # the charm is configured to serve tests.
    if in_staging and not serve_tests:
        build_dirname = 'build-debug'
    else:
        build_dirname = 'build-prod'
    build_dir = os.path.join(JUJU_GUI_DIR, build_dirname)
    log('Generating the Juju GUI configuration file.')
    user, password = ('admin', 'admin') if in_staging else (None, None)
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
        'readonly': json.dumps(readonly),
        'user': json.dumps(user),
        'protocol': json.dumps(protocol)
    }
    if config_js_path is None:
        config_js_path = os.path.join(
            build_dir, 'juju-ui', 'assets', 'config.js')
    render_to_file('config.js.template', context, config_js_path)
    log('Generating the nginx site configuration file.')
    context = {
        'port': WEB_PORT,
        'serve_tests': serve_tests,
        'server_root': build_dir,
        'tests_root': os.path.join(JUJU_GUI_DIR, 'test', ''),
    }
    render_to_file('nginx-site.template', context, nginx_path)
    log('Generating haproxy configuration file.')
    context = {
        'api_pem': JUJU_PEM,
        'api_port': API_PORT,
        'ssl_cert_path': ssl_cert_path,
        # Use the same certificate for both HTTPS and Websocket connections.
        # In the long term, we want separate certs to be used here.
        'web_pem': JUJU_PEM,
        'web_port': WEB_PORT,
        'secure': secure
    }
    render_to_file('haproxy.cfg.template', context, haproxy_path)
    log('Starting Juju GUI.')
    with su('root'):
        # Start the Juju GUI.
        service_control(NGINX, START)
        service_control(HAPROXY, START)


def stop(in_staging):
    """Stop the Juju API agent."""
    with su('root'):
        log('Stopping Juju GUI.')
        service_control(HAPROXY, STOP)
        service_control(NGINX, STOP)
        if in_staging:
            log('Stopping the staging backend.')
            service_control(IMPROV, STOP)
        else:
            log('Stopping API agent.')
            service_control(AGENT, STOP)


def fetch_gui(juju_gui_source, logpath):
    """Retrieve the Juju GUI release/branch."""
    # Retrieve a Juju GUI release.
    origin, version_or_branch = parse_source(juju_gui_source)
    if origin == 'branch':
        # Make sure we have the dependencies necessary for us to actually make
        # a build.
        _get_build_dependencies()
        # Create a release starting from a branch.
        juju_gui_source_dir = os.path.join(CURRENT_DIR, 'juju-gui-source')
        log('Retrieving Juju GUI source checkout from %s.' % version_or_branch)
        cmd_log(run('rm', '-rf', juju_gui_source_dir))
        cmd_log(bzr_checkout(version_or_branch, juju_gui_source_dir))
        log('Preparing a Juju GUI release.')
        logdir = os.path.dirname(logpath)
        fd, name = tempfile.mkstemp(prefix='make-distfile-', dir=logdir)
        log('Output from "make distfile" sent to %s' % name)
        with environ(NO_BZR='1'):
            run('make', '-C', juju_gui_source_dir, 'distfile',
                stdout=fd, stderr=fd)
        release_tarball = first_path_in_dir(
            os.path.join(juju_gui_source_dir, 'releases'))
    else:
        # Retrieve a release from Launchpad.
        log('Retrieving Juju GUI release.')
        launchpad = Launchpad.login_anonymously('Juju GUI charm', 'production')
        project = launchpad.projects['juju-gui']
        file_url = get_release_file_url(project, origin, version_or_branch)
        log('Downloading release file from %s.' % file_url)
        release_tarball = os.path.join(CURRENT_DIR, 'release.tgz')
        cmd_log(run('curl', '-L', '-o', release_tarball, file_url))
    return release_tarball


def fetch_api(juju_api_branch):
    """Retrieve the Juju branch."""
    # Retrieve Juju API source checkout.
    log('Retrieving Juju API source checkout.')
    cmd_log(run('rm', '-rf', JUJU_DIR))
    cmd_log(bzr_checkout(juju_api_branch, JUJU_DIR))


def setup_gui(release_tarball):
    """Set up Juju GUI."""
    # Uncompress the release tarball.
    log('Installing Juju GUI.')
    release_dir = os.path.join(CURRENT_DIR, 'release')
    cmd_log(run('rm', '-rf', release_dir))
    os.mkdir(release_dir)
    uncompress = command('tar', '-x', '-z', '-C', release_dir, '-f')
    cmd_log(uncompress(release_tarball))
    # Link the Juju GUI dir to the contents of the release tarball.
    cmd_log(run('ln', '-sf', first_path_in_dir(release_dir), JUJU_GUI_DIR))


def setup_nginx():
    """Set up nginx."""
    log('Setting up nginx.')
    nginx_default_site = '/etc/nginx/sites-enabled/default'
    if os.path.exists(nginx_default_site):
        os.remove(nginx_default_site)
    if not os.path.exists(JUJU_GUI_SITE):
        cmd_log(run('touch', JUJU_GUI_SITE))
        cmd_log(run('chown', 'ubuntu:', JUJU_GUI_SITE))
        cmd_log(
            run('ln', '-s', JUJU_GUI_SITE,
                '/etc/nginx/sites-enabled/juju-gui'))


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
