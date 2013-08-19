# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2013 Canonical Ltd.
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

"""Blocking functions and objects for handling bundle deployments.

The following functions and objects use the juju-deployer library to handle
bundle deployments. They are intended to be run in a separate process.
Code interacting with the juju-deployer should be stored here.
"""

from deployer.action.importer import Importer
from deployer.deployment import Deployment
from deployer.env import GoEnvironment
from tornado import util


IMPORTER_OPTIONS = util.ObjectDict(
    branch_only=False,  # Avoid just updating VCS branches and exiting.
    deploy_delay=0,  # Do not sleep between 'deploy' commands.
    no_local_mods=True,  # Disallow deployment of locally-modified charms.
    overrides=None,  # Do not override config options.
    rel_wait=60,  # Wait for 1 minute before checking for relation errors.
    retry_count=0,  # Do not retry on unit errors.
    timeout=45*60,  # Set a 45 minutes timeout for the entire deployment.
    update_charms=False,  # Do not update existing charm branches.
    watch=False,  # Do not watch environment changes on console.
)


class _Environment(GoEnvironment):
    """A Juju environment for the juju-deployer.

    Add support for deployments via the Juju API and for authenticating with
    the provided password.
    """

    def __init__(self, endpoint, password):
        super(_Environment, self).__init__('go', endpoint=endpoint)
        self._password = password

    def _get_token(self):
        """Return the stored password.

        This method is overridden so that the juju-deployer does not try to
        parse the environment.yaml file in order to retrieve the admin-secret.
        """
        return self._password

    def connect(self):
        """Connect the API client to the Juju backend.

        This method is overridden so that a call to connect is a no-op if the
        client is already connected.
        """
        if self.client is None:
            super(_Environment, self).connect()

    def close(self):
        """Close the API connection.

        Also set the client attribute to None after the disconnection.
        """
        super(_Environment, self).close()
        self.client = None

    def deploy(
            self, name, charm_url, config=None, constraints=None, num_units=1,
            *args, **kwargs):
        """Deploy a service using the API.

        Using the API in place of the command line introduces some limitations:
          - it is not possible to use a local charm/repository;
          - it is not possible to deploy to a specific machine.
        """
        self.client.deploy(
            name, charm_url, config=config, constraints=constraints,
            num_units=num_units)


def _validate(env, bundle):
    """Bundle validation logic, used by both validate and import_bundle.

    This function receives a connected environment and the bundle as a YAML
    decoded object.
    """
    # Retrieve the services deployed in the Juju environment.
    env_status = env.status()
    env_services = env_status['services'].keys()
    # Retrieve the services in the bundle.
    bundle_services = bundle.get('services', {}).keys()
    # Calculate overlapping services.
    overlapping = [i for i in env_services if i in bundle_services]
    if overlapping:
        services = ', '.join(overlapping)
        error = 'service(s) already in the environment: {}'.format(services)
        raise ValueError(error)


def validate(apiurl, password, bundle):
    """Validate a bundle."""
    env = _Environment(apiurl, password)
    env.connect()
    try:
        _validate(env, bundle)
    finally:
        env.close()


def import_bundle(apiurl, password, name, bundle):
    """Import a bundle."""
    env = _Environment(apiurl, password)
    deployment = Deployment(name, bundle, [])
    importer = Importer(env, deployment, IMPORTER_OPTIONS)
    env.connect()
    try:
        _validate(env, bundle)
        importer.run()
    finally:
        env.close()
