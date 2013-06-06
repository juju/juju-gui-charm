"""Juju GUI helpers tests."""

import json
import unittest

import mock

from helpers import (
    command,
    juju_destroy_service,
    juju_status,
    legacy_juju,
    ProcessError,
    retry,
    wait_for_service,
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


@mock.patch('helpers.juju')
@mock.patch('helpers.juju_status')
class TestJujuDestroyService(unittest.TestCase):

    service = 'test-service'
    env = 'test-env'

    def test_service_destroyed(self, mock_juju_status, mock_juju):
        # The juju destroy-service command is correctly called.
        mock_juju_status.return_value = {}
        with mock.patch('helpers.jujuenv', self.env):
            juju_destroy_service(self.service)
        self.assertEqual(1, mock_juju_status.call_count)
        mock_juju.assert_called_once_with(
            'destroy-service', '-e', self.env, self.service)

    def test_wait_until_removed(self, mock_juju_status, mock_juju):
        # The function waits for the service to be removed.
        mock_juju_status.side_effect = (
            {'services': {self.service: {}, 'another-service': {}}},
            {'services': {'another-service': {}}},
        )
        with mock.patch('helpers.jujuenv', self.env):
            juju_destroy_service(self.service)
        self.assertEqual(2, mock_juju_status.call_count)
        mock_juju.assert_called_once_with(
            'destroy-service', '-e', self.env, self.service)


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
        with mock.patch('helpers.jujuenv', 'test-env'):
            status = juju_status()
        self.assertEqual(self.status, status)
        mock_juju.assert_called_once_with(
            'status', '-e', 'test-env', '--format', 'json')


@mock.patch('helpers.juju')
class TestLegacyJuju(unittest.TestCase):

    def test_pyjuju(self, mock_juju):
        # Legacy Juju is correctly recognized.
        mock_juju.return_value = '0.7.0'
        self.assertTrue(legacy_juju())
        mock_juju.assert_called_once_with('--version')

    def test_juju_core(self, mock_juju):
        # juju-core is correctly recognized.
        mock_juju.side_effect = ProcessError(1, 'command failed', '', '')
        self.assertFalse(legacy_juju())
        mock_juju.assert_called_once_with('--version')


class TestProcessError(unittest.TestCase):

    def test_str(self):
        # The string representation of the error includes required info.
        err = ProcessError(1, 'mycommand', 'myoutput', 'myerror')
        expected = (
            "Command 'mycommand' returned non-zero exit status 1. "
            'Output: myoutput Error: myerror'
        )
        self.assertEqual(expected, str(err))


class TestRetry(unittest.TestCase):

    error = 'error after {} tries'

    def setUp(self):
        self.tries = 0

    @retry(TypeError, tries=10, delay=0)
    def success(self):
        self.tries += 1
        if self.tries == 5:
            return True
        raise TypeError

    @retry(TypeError, tries=10, delay=0)
    def failure(self):
        self.tries += 1
        raise TypeError(self.error.format(self.tries))

    def test_success(self):
        # The decorated function returns without errors after several tries.
        self.assertTrue(self.success())

    def test_failure(self):
        # The decorated function raises the last error.
        with self.assertRaises(TypeError) as info:
            self.failure()
        self.assertEqual(self.error.format(10), str(info.exception))


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
        address = wait_for_service(self.service)
        self.assertEqual(self.address, address)
        self.assertEqual(3, mock_juju_status.call_count)

    def test_service_not_exposed(self, mock_juju_status):
        # The function waits until the service is exposed.
        mock_juju_status.side_effect = (
            self.get_status(exposed=False), self.get_status(),
        )
        address = wait_for_service(self.service)
        self.assertEqual(self.address, address)
        self.assertEqual(2, mock_juju_status.call_count)

    def test_unit_not_ready(self, mock_juju_status):
        # The function waits until the unit is created.
        mock_juju_status.side_effect = (
            {'services': {'juju-gui': {}}},
            {'services': {'juju-gui': {'units': {}}}},
            self.get_status(),
        )
        address = wait_for_service(self.service)
        self.assertEqual(self.address, address)
        self.assertEqual(3, mock_juju_status.call_count)

    def test_state_error(self, mock_juju_status):
        # An error is raised if the unit is in an error state.
        mock_juju_status.return_value = self.get_status(state='install-error')
        self.assertRaises(RuntimeError, wait_for_service, self.service)
        self.assertEqual(1, mock_juju_status.call_count)

    def test_not_started(self, mock_juju_status):
        # The function waits until the unit is in a started state.
        mock_juju_status.side_effect = (
            self.get_status(state='pending'), self.get_status(),
        )
        address = wait_for_service(self.service)
        self.assertEqual(self.address, address)
        self.assertEqual(2, mock_juju_status.call_count)

    def test_unit_number(self, mock_juju_status):
        # Different unit names are correctly handled.
        mock_juju_status.return_value = self.get_status(unit=42)
        address = wait_for_service(self.service)
        self.assertEqual(self.address, address)
        self.assertEqual(1, mock_juju_status.call_count)

    def test_public_address(self, mock_juju_status):
        # The public address is returned when the service is ready.
        mock_juju_status.return_value = self.get_status()
        address = wait_for_service(self.service)
        self.assertEqual(self.address, address)
        self.assertEqual(1, mock_juju_status.call_count)
