"""Juju GUI deploy helper."""

from __future__ import print_function
import os
import tempfile

from charmhelpers import make_charm_config_file

from helpers import (
    command,
    juju,
    jujuenv,
    ProcessError,
    retry,
    wait_for_service,
)


rsync = command('rsync', '-a', '--exclude', '.bzr', '--exclude', '.venv')


def setup_repository():
    """Create a temporary Juju repository to use for charm deployment.

    Copy the current charm files in the precise repository section, excluding
    the virtualenv and Bazaar directories. Return the repository path.
    """
    current_dir = os.path.dirname(__file__)
    source = os.path.abspath(os.path.join(current_dir, '..'))
    repo = tempfile.mkdtemp()
    destination = os.path.join(repo, 'precise')
    os.makedirs(destination)
    rsync(source, destination)
    return repo


@retry(ProcessError)
def juju_deploy(charm, options=None, force_machine=None):
    """Deploy and expose the charm. Return the first unit's public address.

    Also wait until the service is exposed and the first unit started.
    If options are provided, they will be used when deploying the charm.
    If force_machine is not None, create the unit in the specified machine.
    """
    repo = setup_repository()
    args = ['deploy', '-e', jujuenv, '--repository', repo]
    if options is not None:
        config_file = make_charm_config_file({charm: options})
        args.extend(['--config', config_file.name])
    if force_machine is not None:
        args.extend(['--force-machine', str(force_machine)])
    args.append('local:{0}'.format(charm))
    juju(*args)
    juju('expose', '-e', jujuenv, charm)
    address = wait_for_service(charm)
    return address


if __name__ == '__main__':
    address = juju_deploy('juju-gui')
    print(address)
