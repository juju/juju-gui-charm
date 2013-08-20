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

"""Bundle deployment utility functions."""

from functools import wraps
import logging

from tornado import gen


def change(deployment_id, status, queue=None, error=None):
    """Return a dict representing a deployment change."""
    result = {'DeploymentId': deployment_id, 'Status': status}
    if queue is not None:
        result['Queue'] = queue
    if error is not None:
        result['Error'] = error
    return result


def require_authenticated_user(view):
    """Require the user to be authenticated when executing the decorated view.

    This function can be used to decorate bundle views. Each view receives
    a request and a deployer, and the user instance is stored in request.user.
    If the user is not authenticated an error response is raised when calling
    the view. Otherwise, the view is executed normally.
    """
    @wraps(view)
    def decorated(request, deployer):
        if not request.user.is_authenticated:
            raise response(error='unauthorized access: no user logged in')
        return view(request, deployer)
    return decorated


def response(info=None, error=None):
    """Create a response containing the given (optional) info and error values.

    This function is intended to be used by bundles views.
    Return a gen.Return instance, so that the result of this method can easily
    be raised from coroutines.
    """
    if info is None:
        info = {}
    data = {'Response': info}
    if error is not None:
        logging.error('deployer: {}'.format(error))
        data['Error'] = error
    return gen.Return(data)
