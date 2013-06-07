"""Juju GUI helpers tests."""

import json
import unittest

import mock

from helpers import (
    command,
    juju,
    juju_destroy_service,
    juju_status,
    legacy_juju,
    ProcessError,
    retry,
    wait_for_unit,
)


class TestCommand(unittest.TestCase):

    def test_simple_command(self):
        # Creating a simple command (ls) works and running the command
        # produces a string.
        ls = command('/bin/ls')
        self.assertIsInstance(ls(), str)

    def test_arguments(self):
        # Arguments can be passed to commands.
        ls = command('/bin/ls')
        self.assertIn('Usage:', ls('--help'))

    def test_missing(self):
        # If the command does not exist, an OSError (No such file or
        # directory) is raised.
        bad = command('this command does not exist')
        with self.assertRaises(OSError) as info:
            bad()
        self.assertEqual(2, info.exception.errno)

    def test_error(self):
        # If the command returns a non-zero exit code, an exception is raised.
        bad = command('/bin/ls', '--not a valid switch')
        self.assertRaises(ProcessError, bad)

    def test_baked_in_arguments(self):
        # Arguments can be passed when creating the command as well as when
        # executing it.
        ll = command('/bin/ls', '-al')
        self.assertIn('rw', ll())  # Assumes a file is r/w in the pwd.
        self.assertIn('Usage:', ll('--help'))

    def test_quoting(self):
        # There is no need to quote special shell characters in commands.
        ls = command('/bin/ls')
        ls('--help', '>')


@mock.patch('helpers.juju_command')
class TestJuju(unittest.TestCase):

    env = 'test-env'
    patch_environ = mock.patch('os.environ', {'JUJU_ENV': env})
    process_error = ProcessError(1, 'an error occurred', 'output', 'error')

    def test_e_in_args(self, mock_juju_command):
        # The command includes the environment provided with -e.
        with self.patch_environ:
            juju('deploy', '-e', 'another-env', 'test-charm')
        mock_juju_command.assert_called_once_with(
            'deploy', '-e', 'another-env', 'test-charm')

    def test_environment_in_args(self, mock_juju_command):
        # The command includes the environment provided with --environment.
        with self.patch_environ:
            juju('deploy', '--environment', 'another-env', 'test-charm')
        mock_juju_command.assert_called_once_with(
            'deploy', '--environment', 'another-env', 'test-charm')

    def test_environment_in_context(self, mock_juju_command):
        # The command includes the environment if found in the context as
        # the environment variable JUJU_ENV.
        with self.patch_environ:
            juju('deploy', 'test-charm')
        mock_juju_command.assert_called_once_with(
            'deploy', '-e', self.env, 'test-charm')

    def test_environment_not_in_context(self, mock_juju_command):
        # The command does not include the environment if not found in the
        # context as the environment variable JUJU_ENV.
        with mock.patch('os.environ', {}):
            juju('deploy', 'test-charm')
        mock_juju_command.assert_called_once_with('deploy', 'test-charm')

    def test_handle_process_errors(self, mock_juju_command):
        # The command retries several times before failing if a ProcessError is
        # raised.
        mock_juju_command.side_effect = ([self.process_error] * 9) + ['value']
        with mock.patch('time.sleep') as mock_sleep:
            with mock.patch('os.environ', {}):
                result = juju('deploy', 'test-charm')
        self.assertEqual('value', result)
        self.assertEqual(10, mock_juju_command.call_count)
        mock_juju_command.assert_called_with('deploy', 'test-charm')
        self.assertEqual(9, mock_sleep.call_count)
        mock_sleep.assert_called_with(1)

    def test_raise_process_errors(self, mock_juju_command):
        # The command raises the last ProcessError after a number of retries.
        mock_juju_command.side_effect = [self.process_error] * 10
        with mock.patch('time.sleep') as mock_sleep:
            with mock.patch('os.environ', {}):
                with self.assertRaises(ProcessError) as info:
                    juju('deploy', 'test-charm')
        self.assertIs(self.process_error, info.exception)
        self.assertEqual(10, mock_juju_command.call_count)
        mock_juju_command.assert_called_with('deploy', 'test-charm')
        self.assertEqual(10, mock_sleep.call_count)
        mock_sleep.assert_called_with(1)


@mock.patch('helpers.juju')
@mock.patch('helpers.juju_status')
class TestJujuDestroyService(unittest.TestCase):

    service = 'test-service'

    def test_service_destroyed(self, mock_juju_status, mock_juju):
        # The juju destroy-service command is correctly called.
        mock_juju_status.return_value = {}
        juju_destroy_service(self.service)
        self.assertEqual(1, mock_juju_status.call_count)
        mock_juju.assert_called_once_with('destroy-service', self.service)

    def test_wait_until_removed(self, mock_juju_status, mock_juju):
        # The function waits for the service to be removed.
        mock_juju_status.side_effect = (
            {'services': {self.service: {}, 'another-service': {}}},
            {'services': {'another-service': {}}},
        )
        juju_destroy_service(self.service)
        self.assertEqual(2, mock_juju_status.call_count)
        mock_juju.assert_called_once_with('destroy-service', self.service)


class TestJujuStatus(unittest.TestCase):

    status = {
        'machines': {
            '0': {'agent-state': 'running', 'dns-name': 'ec2.example.com'},
        },
        'services': {
            'juju-gui': {'charm': 'cs:precise/juju-gui-48', 'exposed': True},
        },
    }

    @mock.patch('helpers.juju')
    def test_status(self, mock_juju):
        # The function returns the unserialized juju status.
        mock_juju.return_value = json.dumps(self.status)
        status = juju_status()
        self.assertEqual(self.status, status)
        mock_juju.assert_called_once_with('status', '--format', 'json')


@mock.patch('helpers.juju_command')
class TestLegacyJuju(unittest.TestCase):

    def test_pyjuju(self, mock_juju_command):
        # Legacy Juju is correctly recognized.
        mock_juju_command.return_value = '0.7.0'
        self.assertTrue(legacy_juju())
        mock_juju_command.assert_called_once_with('--version')

    def test_juju_core(self, mock_juju_command):
        # juju-core is correctly recognized.
        mock_juju_command.side_effect = ProcessError(1, 'failed', '', '')
        self.assertFalse(legacy_juju())
        mock_juju_command.assert_called_once_with('--version')


class TestProcessError(unittest.TestCase):

    def test_str(self):
        # The string representation of the error includes required info.
        err = ProcessError(1, 'mycommand', 'myoutput', 'myerror')
        expected = (
            "Command 'mycommand' returned non-zero exit status 1. "
            "Output: 'myoutput'. Error: 'myerror'."
        )
        self.assertEqual(expected, str(err))


@mock.patch('time.sleep')
class TestRetry(unittest.TestCase):

    retry_type_error = retry(TypeError, tries=10, delay=1)
    result = 'my value'

    def make_callable(self, side_effect):
        mock_callable = mock.Mock()
        mock_callable.side_effect = side_effect
        mock_callable.__name__ = 'mock_callable'  # Required by wraps.
        decorated = retry(TypeError, tries=5, delay=1)(mock_callable)
        return mock_callable, decorated

    def test_immediate_success(self, mock_sleep):
        # The decorated function returns without retrying if no errors occur.
        mock_callable, decorated = self.make_callable([self.result])
        result = decorated()
        self.assertEqual(self.result, result)
        self.assertEqual(1, mock_callable.call_count)
        self.assertFalse(mock_sleep.called)

    def test_success(self, mock_sleep):
        # The decorated function returns without errors after several tries.
        side_effect = ([TypeError] * 4) + [self.result]
        mock_callable, decorated = self.make_callable(side_effect)
        result = decorated()
        self.assertEqual(self.result, result)
        self.assertEqual(5, mock_callable.call_count)
        self.assertEqual(4, mock_sleep.call_count)
        mock_sleep.assert_called_with(1)

    def test_failure(self, mock_sleep):
        # The decorated function raises the last error.
        mock_callable, decorated = self.make_callable([TypeError] * 5)
        self.assertRaises(TypeError, decorated)
        self.assertEqual(5, mock_callable.call_count)
        self.assertEqual(5, mock_sleep.call_count)
        mock_sleep.assert_called_with(1)


@mock.patch('helpers.juju_status')
class TestWaitForService(unittest.TestCase):

    address = 'unit.example.com'
    service = 'test-service'

    def get_status(self, state='started', exposed=True, unit=0):
        """Return a dict-like Juju status."""
        unit_name = '{}/{}'.format(self.service, unit)
        return {
            'services': {
                self.service: {
                    'exposed': exposed,
                    'units': {
                        unit_name: {
                            'agent-state': state,
                            'public-address': self.address,
                        }
                    },
                },
            },
        }

    def test_service_not_deployed(self, mock_juju_status):
        # The function waits until the service is deployed.
        mock_juju_status.side_effect = (
            {}, {'services': {}}, self.get_status(),
        )
        unit_info = wait_for_unit(self.service)
        self.assertEqual(self.address, unit_info['public-address'])
        self.assertEqual(3, mock_juju_status.call_count)

    def test_service_not_exposed(self, mock_juju_status):
        # The function waits until the service is exposed.
        mock_juju_status.side_effect = (
            self.get_status(exposed=False), self.get_status(),
        )
        unit_info = wait_for_unit(self.service)
        self.assertEqual(self.address, unit_info['public-address'])
        self.assertEqual(2, mock_juju_status.call_count)

    def test_unit_not_ready(self, mock_juju_status):
        # The function waits until the unit is created.
        mock_juju_status.side_effect = (
            {'services': {'juju-gui': {}}},
            {'services': {'juju-gui': {'units': {}}}},
            self.get_status(),
        )
        unit_info = wait_for_unit(self.service)
        self.assertEqual(self.address, unit_info['public-address'])
        self.assertEqual(3, mock_juju_status.call_count)

    def test_state_error(self, mock_juju_status):
        # An error is raised if the unit is in an error state.
        mock_juju_status.return_value = self.get_status(state='install-error')
        self.assertRaises(RuntimeError, wait_for_unit, self.service)
        self.assertEqual(1, mock_juju_status.call_count)

    def test_not_started(self, mock_juju_status):
        # The function waits until the unit is in a started state.
        mock_juju_status.side_effect = (
            self.get_status(state='pending'), self.get_status(),
        )
        unit_info = wait_for_unit(self.service)
        self.assertEqual(self.address, unit_info['public-address'])
        self.assertEqual(2, mock_juju_status.call_count)

    def test_unit_number(self, mock_juju_status):
        # Different unit names are correctly handled.
        mock_juju_status.return_value = self.get_status(unit=42)
        unit_info = wait_for_unit(self.service)
        self.assertEqual(self.address, unit_info['public-address'])
        self.assertEqual(1, mock_juju_status.call_count)

    def test_public_address(self, mock_juju_status):
        # The public address is returned when the service is ready.
        mock_juju_status.return_value = self.get_status()
        unit_info = wait_for_unit(self.service)
        self.assertEqual(self.address, unit_info['public-address'])
        self.assertEqual(1, mock_juju_status.call_count)
