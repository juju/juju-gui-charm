"""Juju GUI charm utilities."""

__all__ = [
    'AGENT',
    'bzr_checkout',
    'cmd_log',
    'CURRENT_DIR',
    'fetch_api',
    'fetch_gui',
    'first_path_in_dir',
    'get_release_file_url',
    'get_zookeeper_address',
    'GUI',
    'IMPROV',
    'JUJU_DIR',
    'JUJU_GUI_DIR',
    'parse_source',
    'render_to_file',
    'setup_gui',
    'setup_nginx',
    'start_agent',
    'start_gui',
    'start_improv',
    'stop',
]

import json
import os
import logging
import tempfile

from launchpadlib.launchpad import Launchpad
from shelltoolbox import (
    command,
    environ,
    run,
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
GUI = 'juju-gui'
CURRENT_DIR = os.getcwd()
JUJU_DIR = os.path.join(CURRENT_DIR, 'juju')
JUJU_GUI_DIR = os.path.join(CURRENT_DIR, 'juju-gui')

# Store the configuration from on invocation to the next.
config_json = Serializer('/tmp/config.json')
# Bazaar checkout command.
bzr_checkout = command('bzr', 'co', '--lightweight')


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
    releases = list(series.releases)
    if not releases:
        raise ValueError('%r: series does not contain releases' % series_name)
    if release_version is None:
        release = releases[0]
    else:
        release = _get_by_attr(releases, 'version', release_version)
        if not release:
            raise ValueError('%r: release not found' % release_version)
    files = [i for i in release.files if str(i).endswith('.tgz')]
    if not files:
        raise ValueError('%r: file not found' % release_version)
    return files[0].file_link


def get_zookeeper_address(agent_file_path):
    """Retrieve the Zookeeper address contained in the given *agent_file_path*.

    The *agent_file_path* is a path to a file containing a line similar to the
    following::

        env JUJU_ZOOKEEPER="address"
    """
    line = search_file('JUJU_ZOOKEEPER', agent_file_path).strip()
    return line.split('=')[1].strip('"')


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


def render_to_file(template, context, destination):
    """Render the given *template* into *destination* using *context*.

    The arguments *template* is the name or path of the template file: it may
    be either a path relative to ``../config`` or an absolute path.
    The argument *destination* is a file path.
    The argument *context* is a dict-like object.
    """
    template_path = os.path.join(
        os.path.dirname(__file__), '..', 'config', template)
    contents = open(template_path).read()
    with open(destination, 'w') as stream:
        stream.write(contents % context)


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
    results_log = logging.getLogger(GUI)


def cmd_log(results):
    global results_log
    if not results:
        return
    if results_log is None:
        _setupLogging()
    # Since 'results' may be multi-line output, start it on a separate line
    # from the logger timestamp, etc.
    results_log.info('\n' + results)


def start_improv(juju_api_port, staging_env,
                 ssl_cert_path='/etc/ssl/private/juju-gui/',
                 config_path='/etc/init/juju-api-improv.conf'):
    """Start a simulated juju environment using ``improv.py``."""
    log('Setting up staging start up script.')
    context = {
        'juju_dir': JUJU_DIR,
        'port': juju_api_port,
        'staging_env': staging_env,
        'keys': ssl_cert_path,
    }
    render_to_file('juju-api-improv.conf.template', context, config_path)
    log('Starting the staging backend.')
    with su('root'):
        service_control(IMPROV, START)


def start_agent(juju_api_port, ssl_cert_path='/etc/ssl/private/juju-gui/',
                config_path='/etc/init/juju-api-agent.conf'):
    """Start the Juju agent and connect to the current environment."""
    # Retrieve the Zookeeper address from the start up script.
    unit_dir = os.path.realpath(os.path.join(CURRENT_DIR, '..'))
    agent_file = '/etc/init/juju-{0}.conf'.format(os.path.basename(unit_dir))
    zookeeper = get_zookeeper_address(agent_file)
    log('Setting up API agent start up script.')
    context = {
        'juju_dir': JUJU_DIR,
        'port': juju_api_port,
        'zookeeper': zookeeper,
        'keys': ssl_cert_path,
    }
    render_to_file('juju-api-agent.conf.template', context, config_path)
    log('Starting API agent.')
    with su('root'):
        service_control(AGENT, START)


def start_gui(juju_api_port, console_enabled, staging,
              config_path='/etc/init/juju-gui.conf',
              nginx_path='/etc/nginx/sites-available/juju-gui',
              config_js_path=None):
    """Set up and start the Juju GUI server."""
    with su('root'):
        run('chown', '-R', 'ubuntu:', JUJU_GUI_DIR)
    build_dir = JUJU_GUI_DIR + '/build-'
    build_dir += 'debug' if staging else 'prod'
    log('Setting up Juju GUI start up script.')
    render_to_file('juju-gui.conf.template', {}, config_path)
    log('Generating the Juju GUI configuration file.')
    context = {
        'address': unit_get('public-address'),
        'console_enabled': json.dumps(console_enabled),
        'port': juju_api_port,
    }
    if config_js_path is None:
        config_js_path = os.path.join(
            build_dir, 'juju-ui', 'assets', 'config.js')
    render_to_file('config.js.template', context, config_js_path)
    log('Generating the nginx site configuration file.')
    context = {
        'server_root': build_dir
    }
    render_to_file('nginx.conf.template', context, nginx_path)
    log('Starting Juju GUI.')
    with su('root'):
        # Start the Juju GUI.
        service_control(GUI, START)


def stop(staging):
    """Stop the Juju API agent."""
    with su('root'):
        log('Stopping Juju GUI.')
        service_control(GUI, STOP)
        if staging:
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
        # Create a release starting from a branch.
        juju_gui_source_dir = os.path.join(CURRENT_DIR, 'juju-gui-source')
        log('Retrieving Juju GUI source checkouts.')
        cmd_log(run('rm', '-rf', juju_gui_source_dir))
        cmd_log(bzr_checkout(version_or_branch, juju_gui_source_dir))
        log('Preparing a Juju GUI release.')
        logdir = os.path.dirname(logpath)
        fd, name = tempfile.mkstemp(prefix='make-distfile-', dir=logdir)
        log('Output from "make distfile" sent to', name)
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


def setup_nginx(ssl_cert_path):
    """Set up nginx."""
    log('Setting up nginx.')
    nginx_default_site = '/etc/nginx/sites-enabled/default'
    juju_gui_site = '/etc/nginx/sites-available/juju-gui'
    if os.path.exists(nginx_default_site):
        os.remove(nginx_default_site)
    if not os.path.exists(juju_gui_site):
        cmd_log(run('touch', juju_gui_site))
        cmd_log(run('chown', 'ubuntu:', juju_gui_site))
        cmd_log(
            run('ln', '-s', juju_gui_site,
                '/etc/nginx/sites-enabled/juju-gui'))
    # Generate the nginx SSL certificates, if needed.
    crt_path = os.path.join(ssl_cert_path, 'juju.crt')
    key_path = os.path.join(ssl_cert_path, 'juju.key')
    if not (os.path.exists(crt_path) and os.path.exists(key_path)):
        if not os.path.exists(ssl_cert_path):
            os.makedirs(ssl_cert_path)
        # See http://superuser.com/questions/226192/openssl-without-prompt
        cmd_log(run(
            'openssl', 'req', '-new', '-newkey', 'rsa:4096',
            '-days', '365', '-nodes', '-x509', '-subj',
            # These are arbitrary test values for the certificate.
            '/C=GB/ST=Juju/L=GUI/O=Ubuntu/CN=juju.ubuntu.com',
            '-keyout', key_path, '-out', crt_path))
