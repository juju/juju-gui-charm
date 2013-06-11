"""Juju GUI test helpers."""

from collections import namedtuple
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


juju_command = command('juju')
juju_env = lambda: os.getenv('JUJU_ENV')  # This is propagated by juju-test.
ssh = command('ssh')
Version = namedtuple('Version', 'major minor patch')


def legacy_juju():
    """Return True if pyJuju is being used, False otherwise."""
    try:
        juju_command('--version')
    except ProcessError:
        return False
    return True


def retry(exception, tries=10, delay=1):
    """If the decorated function raises the exception, wait and try it again.

    Raise the exception raised by the last call if the function does not
    exit normally after the specified number of tries.

    Original from http://wiki.python.org/moin/PythonDecoratorLibrary#Retry.
    """
    def decorator(func):
        @wraps(func)
        def decorated(*args, **kwargs):
            mtries = tries
            while mtries:
                try:
                    return func(*args, **kwargs)
                except exception as err:
                    time.sleep(delay)
                    mtries -= 1
            raise err
        return decorated
    return decorator


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


def juju_version():
    """Return the version of the currently used Juju.

    The version is returned as a named tuple (major, minor, patch).
    If the patch number is missing, it is set to zero.
    """
    pass


def wait_for_unit(sevice):
    """Wait for the first unit of the given service to be started.

    Also wait for the service to be exposed.
    Raise a RuntimeError if the unit is found in an error state.
    Return info about the first unit as a dict containing at least the
    following keys: agent-state, machine, and public-address.
    """
    while True:
        status = juju_status()
        service = status.get('services', {}).get(sevice)
        if service is None or not service.get('exposed'):
            continue
        units = service.get('units', {})
        if not len(units):
            continue
        unit = units.values()[0]
        state = unit['agent-state']
        if 'error' in state:
            raise RuntimeError(
                'the service unit is in an error state: {}'.format(state))
        if state == 'started':
            return unit
