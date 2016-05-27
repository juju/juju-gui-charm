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

"""Juju GUI test helpers."""

from functools import wraps
import json
import os
import subprocess
import time


class ProcessError(subprocess.CalledProcessError):
    """Error running a shell command."""

    def __init__(self, retcode, cmd, output, error):
        super(ProcessError, self).__init__(retcode, cmd, output)
        self.error = error

    def __str__(self):
        msg = super(ProcessError, self).__str__()
        return '{}. Output: {!r}. Error: {!r}.'.format(
            msg, self.output, self.error)


def command(*base_args):
    """Return a callable that will run the given command with any arguments.

    The first argument is the path to the command to run, subsequent arguments
    are command-line arguments to "bake into" the returned callable.

    The callable runs the given executable and also takes arguments that will
    be appended to the "baked in" arguments.

    For example, this code will list a file named "foo" (if it exists):

        ls_foo = command('/bin/ls', 'foo')
        ls_foo()

    While this invocation will list "foo" and "bar" (assuming they exist):

        ls_foo('bar')
    """
    PIPE = subprocess.PIPE

    def runner(*args, **kwargs):
        cmd = base_args + args
        process = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, **kwargs)
        output, error = process.communicate()
        retcode = process.poll()
        if retcode:
            raise ProcessError(retcode, cmd, output, error)
        return output

    return runner


# Define the juju command.
juju_command = command('juju')


def retry(exception, tries=10, delay=1):
    """If the decorated function raises the exception, wait and try it again.

    Raise the exception raised by the first call if the function does not
    exit normally after the specified number of tries.

    Original from http://wiki.python.org/moin/PythonDecoratorLibrary#Retry.
    """
    def decorator(func):
        @wraps(func)
        def decorated(*args, **kwargs):
            tries_remaining = tries
            original_error = None
            while tries_remaining:
                try:
                    return func(*args, **kwargs)
                except Exception as error:
                    if original_error is None:
                        original_error = error
                    time.sleep(delay)
                    tries_remaining -= 1
            raise original_error
        return decorated
    return decorator


@retry(ProcessError)
def juju(command, *args):
    """Call the juju command, passing the model parameters if required.

    The model value can be provided in args, or can be found in the
    context as JUJU_MODEL.
    """
    arguments = [command]
    if ('-m' not in args) and ('--model' not in args):
        model = os.getenv('JUJU_MODEL')
        if model is not None:
            arguments.extend(['-m', model])
    arguments.extend(args)
    return juju_command(*arguments)


def juju_status():
    """Return the Juju status as a dictionary.

    The model in which to operate can be provided in the JUJU_MODEL environment
    variable. If not provided, the currently active model is used.
    """
    status = juju('status', '--format', 'json')
    return json.loads(status)


def wait_for_unit(svc_name):
    """Wait for the first unit of the given svc_name to be started.

    The model in which to operate can be provided in the JUJU_MODEL environment
    variable. If not provided, the currently active model is used.

    Also wait for the service to be exposed.
    Raise a RuntimeError if the unit is found in an error state.
    Return info about the first unit as a dict containing at least the
    following keys: agent-state, machine, and public-address.
    """
    while True:
        status = juju_status()
        service = status.get('services', {}).get(svc_name)
        if service is None or not service.get('exposed'):
            continue
        units = service.get('units', {})
        if not len(units):
            continue
        unit = units.values()[0]
        state = unit.get('agent-state')
        if state is None:
            # Status information for Juju 2.0.
            state = unit['juju-status']['current']
            if state == 'idle':
                return unit
        else:
            if state == 'started':
                return unit
        if 'error' in state:
            raise RuntimeError(
                'the service unit is in an error state: {}'.format(state))


def get_password():
    """Return the password to be used to connect to the Juju API.

    The model in which to operate can be provided in the JUJU_MODEL environment
    variable. If not provided, the currently active model is used.
    """
    output = juju('show-controller', '--show-passwords', '--format', 'json')
    data = json.loads(output)
    account = data.values()[0]['accounts'].values()[0]
    return account['password']
