"""Juju GUI charm utilities."""

import os
import logging

from shelltoolbox import search_file
from charmhelpers import get_config


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

def start_improv(juju_api_port, staging_env):
    """Start a simulated juju environment using ``improv.py``."""
    log('Setting up staging start up script.')
    context = {
        'juju_dir': JUJU_DIR,
        'port': juju_api_port,
        'staging_env': staging_env,
    }
    render_to_file(
        'juju-api-improv.conf.template', context,
        '/etc/init/juju-api-improv.conf')
    log('Starting the staging backend.')
    with su('root'):
        service_control('juju-api-improv', START)
