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

import functools
import itertools
import logging

from concurrent.futures import ThreadPoolExecutor
from tornado.ioloop import IOLoop

from guiserver.bundles import (
    blocking,
    utils,
)
from guiserver.watchers import AsyncWatcher
from guiserver.utils import mkdir
from tornado import gen


# Change statuses.
SCHEDULED = 'scheduled'
STARTED = 'started'
COMPLETED = 'completed'
# Juju API versions supported by the GUI server Deployer.
SUPPORTED_API_VERSIONS = ['go']


class Deployer(object):
    """Handle the bundle deployment process.

    This class provides the logic to validate deployment requests based on the
    current state of the Juju environment, and to start the import process.

    The validation and deployments steps are executed in a separate process.
    It is possible to process only one bundle at the time.

    Note that the Deployer is not intended to store state: it is instantiated
    once when the application is bootstrapped and used as a singleton by all
    WebSocket requests.
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

        # This counter is used to generate deployment identifiers.
        self._deployment_counter = itertools.count()
         # This counter is used to generate watcher identifiers.
        self._watcher_counter = itertools.count()

        # Queue stores the deployment identifiers corresponding to the
        # currently started/queued jobs.
        self._queue = []
        # The _deployments attribute maps deployment identifiers to watchers.
        self._deployments = {}
        # The _watchers attribute maps watcher identifiers to deployment ones.
        self._watchers = {}

        # XXX 2013-08-12 frankban:
            # The following is required because the deployer tries to create
            # the ~/.juju/.deployer-store-cache directory directly, without
            # ensuring that ~/.juju/ actually exists.
        mkdir('~/.juju')

    def _notify_queue(self, deployment_id, position, watcher):
        status = SCHEDULED if position else STARTED
        watcher.put(utils.change(deployment_id, status, queue=position))

    def _on_import_completed(self, deployment_id, future):
        watcher = self._deployments[deployment_id]
        exception = future.exception()
        error = None if exception is None else str(exception)
        watcher.close(utils.change(deployment_id, COMPLETED, error=error))
        self._queue.remove(deployment_id)
        for position, deploy_id in enumerate(self._queue):
            deploy_watcher = self._deployments[deploy_id]
            self._notify_queue(deploy_id, position, deploy_watcher)

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

    def import_bundle(self, user, name, bundle):
        """Import the deployment bundle.

        The deployment is executed in a separate process using the
        juju-deployer library.

        Three arguments are provided:
          - user: the current authenticated user;
          - name: then name of the bundle to be imported;
          - bundle: a YAML decoded object representing the bundle contents.

        Return a Future whose result is a string representing an error or None
        if no error occurred.
        """
        deployment_id = self._deployment_counter.next()
        watcher = AsyncWatcher()
        self._notify_queue(deployment_id, len(self._queue), watcher)
        self._queue.append(deployment_id)
        self._deployments[deployment_id] = watcher
        completed_future = self._run_executor.submit(
            blocking.import_bundle, self._apiurl, user.password, name, bundle)
        completed_callback = functools.partial(
            self._on_import_completed, deployment_id)
        try:
            self._io_loop.add_future(completed_future, completed_callback)
        except Exception as err:
            logging.error(str(err))
            logging.exception(err)
        return deployment_id

    def watch(self, deployment_id):
        if deployment_id not in self._deployments:
            return None
        watcher_id = self._watcher_counter.next()
        self._watchers[watcher_id] = deployment_id
        return watcher_id

    def next(self, watcher_id):
        deployment_id = self._watchers.get(watcher_id)
        if deployment_id is None:
            return
        watcher = self._deployments[deployment_id]
        return watcher.next(watcher_id)

    def status(self):
        watchers = self._deployments.values()
        return [i.getlast() for i in watchers]
