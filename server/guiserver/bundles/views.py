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

"""Bundle deployment views.

This module includes the views used to create responses for bundle deployments
related requests. The bundles protocol, described in the bundles package
docstring, mimics the request/response paradigm over a WebSocket. Views are
simple functions that, given a request, return a response to be sent back to
the API client. Each view receives the following arguments:

    - request: a request object with two attributes:
      - request.params: a dict representing the parameters sent by the client;
      - request.user: the current user (an instance of guiserver.auth.User);
    - deployer: a Deployer instance, ready to be used to schedule/start/observe
      bundle deployments.

The response returned by views must be a Future containing the response data as
a dict-like object, e.g.:

    {'Response': {}, 'Error': 'this field is optional'}

The response function defined in the guiserver.bundles.utils module helps
create these responses:

    from guiserver.bundles.utils import response

    @gen.coroutine
    def succeeding_view(request, deployer)
        raise response('Success!')

    @gen.coroutine
    def failing_view(request, deployer)
        raise response(error='Boo!')

Use the require_authenticated_user decorator if the view requires a logged in
user, e.g.:

    @gen.coroutine
    @require_authenticated_user
    def protected_view(request, deployer):
        # This function body is executed only if the user is authenticated.

As seen in the examples above, views are also coroutines: they must be
decorated with tornado.gen.coroutine, they can suspend their own execution
using "yield", and they must return their results using "raise response(...)"
(the latter will be eventually fixed switching to a newer version of Python).
"""

import datetime
import logging
import uuid

from jujubundlelib import (
    changeset,
    validate,
)
from tornado import gen
from tornado.ioloop import IOLoop
import yaml

from guiserver.bundles.utils import (
    prepare_bundle,
    require_authenticated_user,
    response,
)


def _validate_import_params(params):
    """Parse the request data and return a (name, bundle, bundle_id) tuple.

    In the tuple:
      - name is the name of the bundle to be imported; this is required for old
        style bundles, not for v4 bundles
      - bundle is the YAML decoded bundle object.
      - bundle_id is the permanent id of the bundle, in v3 of the form
        ~user/basketname/version/bundlename, e.g.
        ~jorge/mediawiki/3/mediawiki-simple.  The bundle_id is optional and
        will be None if not given.
        In v4, the bundle ID is in the form ~user/bundlename, e.g.
        ~jorge/mediawiki-simple and is required.

    Raise a ValueError if data represents an invalid request.
    """
    bundle_id = params.get('BundleID')
    contents = params.get('YAML')
    if contents is None:
        raise ValueError('invalid data parameters')
    try:
        bundles = yaml.safe_load(contents)
    except Exception as err:
        raise ValueError('invalid YAML contents: {}'.format(err))
    if params.get('Version') == 4:
        return 'bundle-v4', bundles, bundle_id

    # This is an old-style bundle.
    name = params.get('Name')
    if name is None:
        # The Name is optional if the YAML contents contain only one bundle.
        if len(bundles) == 1:
            name = bundles.keys()[0]
        else:
            raise ValueError(
                'invalid data parameters: no bundle name provided')
    bundle = bundles.get(name)
    if bundle is None:
        raise ValueError('bundle {} not found'.format(name))
    return name, bundle, bundle_id


@gen.coroutine
@require_authenticated_user
def import_bundle(request, deployer):
    """Start or schedule a bundle deployment.

    If the request is valid, the response will contain the DeploymentId
    assigned to the bundle deployment.

    Request: 'Import'.
    Parameters example: {
        'Name': 'bundle-name',
        'YAML': 'bundles',
        'Version': 4,
        'BundleID': '~user/bundle-name',
    }.
    """
    # Validate the request parameters.
    try:
        name, bundle, bundle_id = _validate_import_params(request.params)
    except ValueError as err:
        raise response(error='invalid request: {}'.format(err))
    # Validate and prepare the bundle.
    try:
        prepare_bundle(bundle)
    except ValueError as err:
        error = 'invalid request: invalid bundle {}: {}'.format(name, err)
        raise response(error=error)
    # Validate the bundle against the current state of the Juju environment.
    err = yield deployer.validate(request.user, bundle)
    if err is not None:
        raise response(error='invalid request: {}'.format(err))
    # Add the bundle deployment to the Deployer queue.
    logging.info('import_bundle: scheduling {!r} deployment'.format(name))
    deployment_id = deployer.import_bundle(
        request.user, name, bundle, bundle_id)
    raise response({'DeploymentId': deployment_id})


@gen.coroutine
@require_authenticated_user
def watch(request, deployer):
    """Handle requests for watching a given deployment.

    The deployment is identified in the request by the DeploymentId parameter.
    If the request is valid, the response will contain the WatcherId
    to be used to observe the deployment progress.

    Request: 'Watch'.
    Parameters example: {'DeploymentId': 42}.
    """
    deployment_id = request.params.get('DeploymentId')
    if deployment_id is None:
        raise response(error='invalid request: invalid data parameters')
    # Retrieve a watcher identifier from the Deployer.
    watcher_id = deployer.watch(deployment_id)
    if watcher_id is None:
        raise response(error='invalid request: deployment not found')
    logging.info('watch: deployment {} being observed by watcher {}'.format(
        deployment_id, watcher_id))
    raise response({'WatcherId': watcher_id})


@gen.coroutine
@require_authenticated_user
def next(request, deployer):
    """Wait until a new deployment event is available to be sent to the client.

    The request params must include a WatcherId value, used to identify the
    deployment being observed. If unsent changes are available, a response is
    immediately returned containing the changes. Otherwise, this views suspends
    its execution until a new change is notified by the Deployer.

    Request: 'Next'.
    Parameters example: {'WatcherId': 47}.
    """
    watcher_id = request.params.get('WatcherId')
    if watcher_id is None:
        raise response(error='invalid request: invalid data parameters')
    # Wait for the Deployer to send changes.
    logging.info('next: requested changes for watcher {}'.format(watcher_id))
    changes = yield deployer.next(watcher_id)
    if changes is None:
        raise response(error='invalid request: invalid watcher identifier')
    logging.info('next: returning changes for watcher {}:\n{}'.format(
        watcher_id, changes))
    raise response({'Changes': changes})


@gen.coroutine
@require_authenticated_user
def cancel(request, deployer):
    """Cancel the given pending deployment.

    The deployment is identified in the request by the DeploymentId parameter.
    If the request is not valid or the deployment cannot be cancelled (e.g.
    because it is already started) an error response is returned.

    Request: 'Cancel'.
    Parameters example: {'DeploymentId': 42}.
    """
    deployment_id = request.params.get('DeploymentId')
    if deployment_id is None:
        raise response(error='invalid request: invalid data parameters')
    # Use the Deployer instance to cancel the deployment.
    err = deployer.cancel(deployment_id)
    if err is not None:
        raise response(error='invalid request: {}'.format(err))
    logging.info('cancel: deployment {} cancelled'.format(deployment_id))
    raise response()


@gen.coroutine
@require_authenticated_user
def status(request, deployer):
    """Return the current status of all the bundle deployments.

    The 'Status' request does not receive parameters.
    """
    if request.params:
        params = ', '.join(request.params)
        error = 'invalid request: invalid data parameters: {}'.format(params)
        raise response(error=error)
    last_changes = deployer.status()
    logging.info('status: returning last changes')
    raise response({'LastChanges': last_changes})


# Map bundle tokens to the corresponding set of changes and the expire handle.
_bundle_changesets = {}
# Define the expiration timeout for a bundle token.
_bundle_max_life = datetime.timedelta(minutes=2)


@gen.coroutine
@require_authenticated_user
def get_change_set(request, _):
    """Return a list of changes required to deploy a bundle.

    The bundle can be specified by either passing its YAML content or its
    unique identifier previously stored with a SetChangeSet request
    (see below).

    Request: 'GetChangeSet'.
    Parameters example: {
        'YAML': 'content ...',
    }.
    Parameters example: {
        'Token': 'unique-id',
    }.
    """
    params = request.params
    if len(params) != 1:
        error = 'invalid request: too many data parameters: {}'.format(params)
        raise response(error=error)
    token = params.get('Token')
    if token is not None:
        # Retrieve the change set using the provided token.
        data = _bundle_changesets.pop(token, None)
        if data is None:
            error = 'unknown, fulfilled, or expired bundle token'
            raise response(error=error)
        logging.info('get change set: using token {}'.format(token))
        io_loop = IOLoop.current()
        io_loop.remove_timeout(data['handle'])
        raise response({'ChangeSet': data['changes']})

    # Retrieve the change set using the provided bundle content.
    content = params.get('YAML')
    if content is None:
        error = 'invalid request: expected YAML or Token to be provided'
        raise response(error=error)
    changes, errors = _validate_and_parse_bundle(content)
    if errors:
        raise response({'Errors': errors})
    raise response({'ChangeSet': changes})


@gen.coroutine
@require_authenticated_user
def set_change_set(request, _):
    """Store a change set for the provided bundle YAML content.

    Return a unique identifier that can be used to retrieve the change set
    later. The token expires in two minutes and can be only used once.

    Request: 'SetChangeSet'.
    Parameters example: {
        'YAML': 'content ...',
    }.
    """
    content = request.params.get('YAML')
    if content is None:
        error = 'invalid request: bundle YAML not found'
        raise response(error=error)
    changes, errors = _validate_and_parse_bundle(content)
    if errors:
        raise response({'Errors': errors})

    # Create and store the bundle token.
    token = uuid.uuid4().hex

    def expire_token():
        _bundle_changesets.pop(token, None)
        logging.info('set change set: expired token {}'.format(token))

    io_loop = IOLoop.current()
    handle = io_loop.add_timeout(_bundle_max_life, expire_token)
    now = datetime.datetime.utcnow()
    _bundle_changesets[token] = {
        'changes': changes,
        'handle': handle,
    }
    raise response({
        'Token': token,
        'Created': now.isoformat() + 'Z',
        'Expires': (now + _bundle_max_life).isoformat() + 'Z'
    })


def _validate_and_parse_bundle(content):
    """Validate and parse the given bundle YAML encoded content.

    If the content is valid, return the resulting change set and an empty list
    of errors. Otherwise, return an empty list of changes and a list of errors.
    """
    try:
        bundle = yaml.safe_load(content)
    except Exception:
        error = 'the provided bundle is not a valid YAML'
        return [], [error]
    errors = validate.validate(bundle)
    if errors:
        return [], errors
    return tuple(changeset.parse(bundle)), []
