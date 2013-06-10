"""Juju GUI deploy helper."""

from __future__ import print_function
import json
import os
import tempfile

from charmhelpers import make_charm_config_file

from helpers import (
    command,
    juju,
    wait_for_unit,
)


rsync = command('rsync', '-a', '--exclude', '.bzr', '--exclude', '.venv')


def setup_repository(name, source, series='precise'):
    """Create a temporary Juju repository to use for charm deployment.

    Copy the charm files in source in the precise repository section, using the
    provided charm name and excluding the virtualenv and Bazaar directories.

    Return the repository path.
    """
    source = os.path.abspath(source) + os.path.sep
    repo = tempfile.mkdtemp()
    destination = os.path.join(repo, series, name)
    os.makedirs(destination)
    rsync(source, destination)
    return repo


def juju_deploy(
        charm, options=None, force_machine=None, charm_source=None,
        series='precise'):
    """Deploy and expose the charm. Return the first unit's public address.

    Also wait until the service is exposed and the first unit started.
    If options are provided, they will be used when deploying the charm.
    If force_machine is not None, create the unit in the specified machine.
    If charm_source is None, dynamically retrieve the charm source directory.
    """
    if charm_source is None:
        # Dynamically retrieve the charm source based on the path of this file.
        charm_source = os.path.join(os.path.dirname(__file__), '..')
    repo = setup_repository(charm, charm_source, series=series)
    args = ['deploy', '--repository', repo]
    if options is not None:
        config_file = make_charm_config_file({charm: options})
        args.extend(['--config', config_file.name])
    if force_machine is not None:
        args.extend(['--force-machine', str(force_machine)])
    args.append('local:{}/{}'.format(series, charm))
    juju(*args)
    juju('expose', charm)
    return wait_for_unit(charm)


if __name__ == '__main__':
    unit = juju_deploy('juju-gui')
    print(json.dumps(unit, indent=2))
