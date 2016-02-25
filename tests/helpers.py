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

from collections import namedtuple
from functools import wraps
import json
import logging
import os
import random
import string
import subprocess
import ssl
import time

import websocket
import yaml


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


juju_command = command('juju')
juju_env = lambda: os.getenv('JUJU_ENV')  # This is propagated by juju-test.
ssh = command('ssh')
Version = namedtuple('Version', 'major minor patch')


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


def get_env_attr(attr):
    """Return the requested attribute for the current environment.

    The attr argument is the key included in the current environment section
    in ~/.juju/environments.yaml.
    The environment name must be present in the JUJU_ENV env variable.

    Raise a ValueError if the environment is not found in the context or the
    given environment name is not included in ~/.juju/environments.yaml.
    """
    # Retrieve the current environment.
    env = juju_env()
    if env is None:
        raise ValueError('Unable to retrieve the current environment name.')
    # Load and parse the Juju environments file.
    path = os.path.expanduser('~/.juju/environments.yaml')
    try:
        environments_file = open(path)
    except IOError as err:
        raise ValueError('Unable to open environments file: {}'.format(err))
    try:
        environments = yaml.safe_load(environments_file)
    except Exception as err:
        raise ValueError('Unable to parse environments file: {}'.format(err))
    # Retrieve the admin secret for the current environment.
    try:
        environment = environments.get('environments', {}).get(env)
    except AttributeError as err:
        raise ValueError('Invalid YAML contents: {}'.format(environments))
    if environment is None:
        raise ValueError('Environment {} not found'.format(env))
    value = environment.get(attr)
    if value is None:
        raise ValueError('Attribute {} not found'.format(attr))
    return value


@retry(ProcessError)
def juju(command, *args):
    """Call the juju command, passing the environment parameters if required.

    The environment value can be provided in args, or can be found in the
    context as JUJU_ENV.
    """
    arguments = [command]
    if ('-e' not in args) and ('--environment' not in args):
        env = juju_env()
        if env is not None:
            arguments.extend(['-e', env])
    arguments.extend(args)
    return juju_command(*arguments)


def juju_destroy_service(service):
    """Destroy the given service and wait for the service to be removed."""
    juju('destroy-service', service)
    while True:
        services = juju_status().get('services', {})
        if service not in services:
            return


def juju_status():
    """Return the Juju status as a dictionary."""
    status = juju('status', '--format', 'json')
    return json.loads(status)


def make_service_name(prefix='service-'):
    """Generate a long, random service name."""
    characters = string.ascii_lowercase
    suffix = ''.join([random.choice(characters) for _ in range(20)])
    return prefix + suffix


def stop_services(hostname, services):
    """Stop the given upstart services running on hostname."""
    target = 'ubuntu@{}'.format(hostname)
    for service in services:
        ssh(target, 'sudo', 'service', service, 'stop')


def wait_for_unit(svc_name):
    """Wait for the first unit of the given svc_name to be started.

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
            state = unit['agent-status']['current']
            if state == 'idle':
                return unit
        else:
            if state == 'started':
                return unit
        if 'error' in state:
            raise RuntimeError(
                'the service unit is in an error state: {}'.format(state))


SSLOPT = {
    'cert_reqs': ssl.CERT_NONE,
    'ssl_version': ssl.PROTOCOL_TLSv1,
}


class WebSocketClient(object):
    """A simple blocking WebSocket client used in functional tests."""

    def __init__(self, url):
        self._url = url
        self._conn = None

    def connect(self):
        """Connect to the WebSocket server."""
        logging.info('connecting to {}'.format(self._url))
        self._conn = websocket.create_connection(
            self._url, timeout=10 * 60, sslopt=SSLOPT)

    def send(self, request):
        """Send the given WebSocket request.

        Return the decoded WebSocket response returned by the server.
        Block until the server response is received.
        """
        logging.info('sending message: {}'.format(request))
        self._conn.send(json.dumps(request))
        response = self._conn.recv()
        logging.info('received message: {}'.format(response))
        return json.loads(response)

    def close(self):
        """Close the WebSocket connection."""
        if self._conn is not None:
            logging.info('closing the connection')
            self._conn.close()
            self._conn = None
