"""Juju GUI test helpers."""

from functools import wraps
import json
import os
import subprocess
import time

from charmhelpers import make_charm_config_file


class ProcessError(subprocess.CalledProcessError):
    """Error running a shell command."""

    def __init__(self, retcode, cmd, output, error):
        super(ProcessError, self).__init__(retcode, cmd, output)
        self.error = error

    def __str__(self):
        msg = super(ProcessError, self).__str__()
        return '{}. Output: {} Error: {}'.format(msg, self.output, self.error)


def command(*base_args):
    """Return a callable that will run the given command with any arguments.

    The first argument is the path to the command to run, subsequent arguments
    are command-line arguments to "bake into" the returned callable.

    The callable runs the given executable and also takes arguments that will
    be appeneded to the "baked in" arguments.

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


juju = command('juju')
ssh = command('ssh')
jujuenv = os.getenv('JUJU_ENV')  # This is propagated by juju-test.


def legacy_juju():
    """Return True if pyJuju is being used, False otherwise."""
    try:
        juju('--version')
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
def juju_deploy(charm, options=None, force_machine=None):
    """Deploy and expose the charm. Return the first unit's public address.

    Also wait until the service is exposed and the first unit started.
    If options are provided, they will be used when deploying the charm.
    If force_machine is not None, create the unit in the specified machine.
    """
    args = ['deploy', '-e', jujuenv]
    if options is not None:
        config_file = make_charm_config_file({charm: options})
        args.extend(['--config', config_file.name])
    if force_machine is not None:
        args.extend(['--force-machine', str(force_machine)])
    args.append('local:{0}'.format(charm))
    juju(*args)
    juju('expose', '-e', jujuenv, charm)
    address = wait_for_service(charm)
    return address


@retry(ProcessError)
def juju_destroy_service(service):
    """Destroy the given service and wait for the service to be removed."""
    juju('destroy-service', '-e', jujuenv, service)
    while True:
        services = juju_status().get('services', {})
        if service not in services:
            return


@retry(ProcessError)
def juju_status():
    """Return the Juju status as a dictionary."""
    status = juju('status', '-e', jujuenv, '--format', 'json')
    return json.loads(status)


def wait_for_service(sevice):
    """Wait for the given service to be deployed and exposed.

    Also wait for the first unit in the service to be started.

    Raise a RuntimeError if the unit is found in an error state.
    The juju_status call can raise a ProcessError. In this case, retry two
    times before raising the last process error encountered. This way it is
    possible to handle temporary failures caused, e.g., by disconnections.

    Return the public address of the first unit.
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
            return unit['public-address']
