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
import logging
import os
import tempfile

from charmhelpers.contrib.charmhelpers import make_charm_config_file

from helpers import (
    command,
    get_password,
    juju,
    wait_for_unit,
)


# Define the default series to use when deploying the Juju GUI charm.
DEFAULT_SERIES = 'xenial'
# Define the rsync command.
rsync = command('rsync', '-a',
                '--exclude', '.git',
                '--exclude', '.bzr',
                '--exclude', '/tests')


def juju_deploy(
        charm_name, service_name=None, options=None, force_machine=None,
        charm_source=None, series=None):
    """Deploy and expose the charm. Return the first unit's public address.

    Also wait until the service is exposed and the first unit started.

    If service_name is None, use the name of the charm.
    If options are provided, they will be used when deploying the charm.
    If force_machine is not None, create the unit in the specified machine.
    If charm_source is None, dynamically retrieve the charm source directory.
    If series is None, the series specified in the SERIES environment variable
    is used if found, defaulting to "xenial".
    """
    # Note: this function is used by both the functional tests and
    # "make deploy": see the "if main" section below.
    if charm_source is None:
        # Dynamically retrieve the charm source based on the path of this file.
        charm_source = os.path.join(os.path.dirname(__file__), '..')
    if series is None:
        series = os.getenv('SERIES', '').strip() or DEFAULT_SERIES
    logging.debug('setting up the charm')
    path = tempfile.mkdtemp()
    rsync(charm_source, path)
    args = ['deploy', '--series', series]
    if service_name is None:
        service_name = charm_name
    if options is not None:
        config_file = make_charm_config_file({service_name: options})
        args.extend(['--config', config_file.name])
    if force_machine is not None:
        args.extend(['--to', str(force_machine)])
    args.append(path)
    args.append(service_name)
    logging.debug('deploying {} (series: {}) from {}'.format(
        service_name, series, path))
    juju(*args)
    logging.debug('exposing {}'.format(service_name))
    juju('expose', service_name)
    logging.debug('waiting for the unit to be ready')
    return wait_for_unit(service_name)


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)
    unit = juju_deploy('juju-gui')
    print(json.dumps(unit, indent=2))
    print('password: {}'.format(get_password()))
