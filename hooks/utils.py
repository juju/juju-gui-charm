"""Juju GUI charm utilities."""

__all__ = [
    'AGENT',
    'build',
    'cmd_log',
    'get_zookeeper_address',
    'GUI',
    'IMPROV',
    'render_to_file',
    'start_agent',
    'start_gui',
    'start_improv',
    'stop',
    ]

import json
import os
import logging
import tempfile

from shelltoolbox import (
    cd,
    command,
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


def get_zookeeper_address(agent_file_path):
    """Retrieve the Zookeeper address contained in the given *agent_file_path*.

    The *agent_file_path* is a path to a file containing a line similar to the
    following::

        env JUJU_ZOOKEEPER="address"
    """
    line = search_file('JUJU_ZOOKEEPER', agent_file_path).strip()
    return line.split('=')[1].strip('"')


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
                 config_path='/etc/init/juju-api-improv.conf'):
    """Start a simulated juju environment using ``improv.py``."""
    log('Setting up staging start up script.')
    context = {
        'juju_dir': JUJU_DIR,
        'port': juju_api_port,
        'staging_env': staging_env,
    }
    render_to_file(
        'juju-api-improv.conf.template', context,
        config_path)
    log('Starting the staging backend.')
    with su('root'):
        service_control(IMPROV, START)


def start_agent(juju_api_port, config_path='/etc/init/juju-api-agent.conf'):
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
    }
    render_to_file(
        'juju-api-agent.conf.template', context,
        config_path)
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
    render_to_file(
        'juju-gui.conf.template', {}, config_path)
    log('Generating the Juju GUI configuration file.')
    context = {
        'address': unit_get('public-address'),
        'console_enabled': json.dumps(console_enabled),
        'port': juju_api_port,
    }
    if config_js_path is None:
        config_js_path = os.path.join(
            build_dir, 'juju-ui', 'assets', 'config.js')
    render_to_file(
        'config.js.template', context,
        config_js_path)
    log('Generating the nginx site configuration file.')
    context = {
        'server_root': build_dir
    }
    render_to_file(
        'nginx.conf.template', context, nginx_path)
    log('Starting Juju GUI.')
    with su('root'):
        # Stop nginx so it will restart cleanly with the gui.
        service_control('nginx', STOP)
        service_control(GUI, START)


def stop():
    """Stop the Juju API agent."""
    config = get_config()
    with su('root'):
        log('Stopping Juju GUI.')
        service_control(GUI, STOP)
        if config.get('staging'):
            log('Stopping the staging backend.')
            service_control(IMPROV, STOP)
        else:
            log('Stopping API agent.')
            service_control(AGENT, STOP)


def fetch(juju_gui_branch, juju_api_branch):
    """Install required dependencies and retrieve Juju/Juju GUI branches."""
    log('Retrieving source checkouts.')
    bzr_checkout = command('bzr', 'co', '--lightweight')
    if juju_gui_branch is not None:
        cmd_log(run('rm', '-rf', 'juju-gui'))
        cmd_log(bzr_checkout(juju_gui_branch, 'juju-gui'))
    if juju_api_branch is not None:
        cmd_log(run('rm', '-rf', 'juju'))
        cmd_log(bzr_checkout(juju_api_branch, 'juju'))


def build(logpath):
    """Set up Juju GUI and nginx."""
    log('Building Juju GUI.')
    with cd('juju-gui'):
        logdir = os.path.dirname(logpath)
        fd, name = tempfile.mkstemp(prefix='make-', dir=logdir)
        log('Output from "make" sent to', name)
        run('make', stdout=fd, stderr=fd)
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
