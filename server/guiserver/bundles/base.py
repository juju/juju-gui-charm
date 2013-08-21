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

"""Bundle deployment base objects.

This module defines the base pieces of the bundle support infrastructure,
including the Deployer object, responsible of starting/scheduling deployments,
and the DeployMiddleware, a glue code that connects the WebSocket handler, the
bundle views and the Deployer itself. See the bundles package docstring for
a detailed explanation of how these objects are used.
"""

from concurrent.futures import ThreadPoolExecutor
from tornado import gen
from tornado.ioloop import IOLoop

from guiserver.bundles import (
    blocking,
    utils,
)
from guiserver.utils import (
    add_future,
    mkdir,
)
from guiserver.watchers import WatcherError



# Juju API versions supported by the GUI server Deployer.
SUPPORTED_API_VERSIONS = ['go']


class Deployer(object):
    """Handle the bundle deployment process.

    This class provides the logic to validate deployment requests based on the
    current state of the Juju environment, and to start/observe the import
    process.

    The validation and deployments steps are executed in separate threads.
    It is possible to process only one bundle at the time.

    Note that the Deployer is not intended to store request related state: it
    is instantiated once when the application is bootstrapped and used as a
    singleton by all WebSocket requests.
    """

    def __init__(self, apiurl, apiversion, io_loop=None):
        """Initialize the deployer.

        The apiurl argument is the URL of the juju-core WebSocket server.
        The apiversion argument is the Juju API version (e.g. "go").
        """
        self._apiurl = apiurl
        self._apiversion = apiversion
        if io_loop is None:
            io_loop = IOLoop.current()
        self._io_loop = io_loop

        # This executor is used for validating deployments.
        self._validate_executor = ThreadPoolExecutor(1)
        # This executor is used for processing deployments.
        self._run_executor = ThreadPoolExecutor(1)

        # An observer instance is used to watch the progress of the queued
        # deployment jobs.
        self._observer = utils.Observer()
        # Queue stores the deployment identifiers corresponding to the
        # currently started/queued jobs.
        self._queue = []

        # XXX 2013-08-21 frankban:
            # The following is required because the deployer tries to create
            # the ~/.juju/.deployer-store-cache directory directly, without
            # ensuring that ~/.juju/ actually exists.
        mkdir('~/.juju')

    @gen.coroutine
    def validate(self, user, name, bundle):
        """Validate the deployment bundle.

        The validation is executed in a separate process using the
        juju-deployer library.

        Three arguments are provided:
          - user: the current authenticated user;
          - name: then name of the bundle to be imported;
          - bundle: a YAML decoded object representing the bundle contents.

        Return a Future whose result is a string representing an error or None
        if no error occurred.
        """
        if self._apiversion not in SUPPORTED_API_VERSIONS:
            raise gen.Return('unsupported API version')
        try:
            yield self._validate_executor.submit(
                blocking.validate, self._apiurl, user.password, bundle)
        except Exception as err:
            raise gen.Return(str(err))

    def _import_callback(self, deployment_id, future):
        """Callback called when a deployment process is completed.

        This callback, scheduled in self.import_bundle, receives the
        deployment_id identifying one specific deployment job, and the fired
        future returned by the executor.
        """
        exception = future.exception()
        error = None if exception is None else str(exception)
        # Notify a deployment completed.
        self._observer.notify_completed(deployment_id, error=error)
        # Remove the completed deployment job from the queue.
        self._queue.remove(deployment_id)
        # Notify the new position of all remaining deployments in the queue.
        for position, deploy_id in enumerate(self._queue):
            self._observer.notify_position(deploy_id, position)

    def import_bundle(self, user, name, bundle):
        """Schedule a deployment bundle import process.

        The deployment is executed in a separate thread.

        Three arguments are provided:
          - user: the current authenticated user;
          - name: then name of the bundle to be imported;
          - bundle: a YAML decoded object representing the bundle contents.

        Return the deployment identifier assigned to this deployment process.
        """
        # Start observing this deployment, retrieve the next available
        # deployment id and notify its position at the end of the queue.
        deployment_id = self._observer.add_deployment()
        self._observer.notify_position(deployment_id, len(self._queue))
        # Add this deployment to the queue.
        self._queue.append(deployment_id)
        # Add the import bundle job to the run executor, and set up a callback
        # to be called when the import process completes.
        future = self._run_executor.submit(
            blocking.import_bundle, self._apiurl, user.password, name, bundle)
        add_future(self._io_loop, future, self._import_callback, deployment_id)
        return deployment_id

    def watch(self, deployment_id):
        """Start watching a deployment and return a watcher identifier.

        The watcher identifier can be used by clients to observe changes
        occurring during the deployment process identified by deployment_id.
        Use the returned watcher_id to start observing deployment changes
        (see the self.next() method below).

        Return None if the deployment identifier is not valid.
        """
        if deployment_id in self._observer.deployments:
            return self._observer.add_watcher(deployment_id)

    def next(self, watcher_id):
        """Wait for the next changes on a specific deployment.

        The given watcher identifier refers to a specific deployment process
        (see the self.watch() method above).
        Return a future whose result is a list of deployment changes.
        """
        deployment_id = self._observer.watchers.get(watcher_id)
        if deployment_id is None:
            return
        watcher = self._observer.deployments[deployment_id]
        try:
            return watcher.next(watcher_id)
        except WatcherError:
            return

    def status(self):
        """Return a list containing the last known change for each deployment.
        """
        watchers = self._observer.deployments.values()
        return [i.getlast() for i in watchers]
