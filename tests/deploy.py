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


rsync = command('rsync', '-a', '--exclude', '.bzr', '--exclude', '/tests')


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
        args.extend(['--to', str(force_machine)])
    args.append('local:{}/{}'.format(series, charm))
    juju(*args)
    juju('expose', charm)
    return wait_for_unit(charm)


if __name__ == '__main__':
    unit = juju_deploy('juju-gui')
    print(json.dumps(unit, indent=2))
