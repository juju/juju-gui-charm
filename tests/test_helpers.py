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

"""Juju GUI helpers tests."""

import json
import unittest

import mock

from helpers import (
    command,
    get_password,
    juju,
    juju_status,
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

    model = 'test-model'
    patch_model = mock.patch('os.environ', {'JUJU_MODEL': model})
    process_error = ProcessError(1, 'an error occurred', 'output', 'error')

    def test_m_in_args(self, mock_juju_command):
        # The command includes the model if provided with -m.
        with self.patch_model:
            juju('deploy', '-m', 'another-model', 'test-charm')
        mock_juju_command.assert_called_once_with(
            'deploy', '-m', 'another-model', 'test-charm')

    def test_model_in_args(self, mock_juju_command):
        # The command includes the model if provided with --model.
        with self.patch_model:
            juju('deploy', '--model', 'another-model', 'test-charm')
        mock_juju_command.assert_called_once_with(
            'deploy', '--model', 'another-model', 'test-charm')

    def test_model_in_context(self, mock_juju_command):
        # The command includes the model if found in the context as the
        # environment variable JUJU_MODEL.
        with self.patch_model:
            juju('deploy', 'test-charm')
        mock_juju_command.assert_called_once_with(
            'deploy', '-m', self.model, 'test-charm')

    def test_model_not_in_context(self, mock_juju_command):
        # The command does not include the model if not found in the context as
        # the environment variable JUJU_MODEL.
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

    def test_original_error_reporting(self, *ignored):
        # The exception raised on the first failure is the one that is
        # re-raised if all retries fail, even if a different error is raised
        # subsequently.
        class FirstException(Exception):
            """The first exception the callable will raise."""
        class OtherException(Exception):
            """The exception subsequent calls will raise."""
        side_effect = [FirstException] + [OtherException] * 4
        mock_callable, decorated = self.make_callable(side_effect)
        # If the decorated function never succeeds, the first exception it
        # raised it re-raised after all the retries have been exhausted.
        with self.assertRaises(FirstException):
            decorated()
        # The callable was called several times, it is just that the first
        # exception is re-raised.
        self.assertGreater(mock_callable.call_count, 1)


@mock.patch('helpers.juju_status')
class TestWaitForUnit(unittest.TestCase):

    address = 'unit.example.com'
    service = 'test-service'

    def get_status(self, state='started', exposed=True, unit=0):
        """Return a dict-like Juju status."""
        unit_name = '{}/{}'.format(self.service, unit)
        return {
            'applications': {
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


controller_info = """
{
  "lxd": {
    "models": {
      "admin": {
            "uuid": "410c3d1b-00a6-4984-809f-09f32ea9c0a4"
      },
      "default": {
            "uuid": "3af96b8e-1f44-45a3-8b8e-9362e1e47119"
      }
    },
    "current-model": "admin@local/default",
    "account": {
      "password": "d409fc4ae870ab66292007ff9dfdd67f",
      "user": "admin@local"
    },
    "details": {
      "ca-cert": "my-cert",
      "uuid": "410c3d1b-00a6-4984-809f-09f32ea9c0a4",
      "api-endpoints": [
        "10.0.42.139:17070"
      ],
      "cloud": "lxd",
      "region": "localhost",
      "uuid": "e4053c3c-b8bd-432b-895b-1099c7d109ea"
    }
  }
}
"""


class TestGetPassword(unittest.TestCase):

    def test_password(self):
        # The controller admin password is correctly retrieved.
        with mock.patch('helpers.juju') as mock_juju:
            mock_juju.return_value = controller_info
            password = get_password()
        self.assertEqual('d409fc4ae870ab66292007ff9dfdd67f', password)
        mock_juju.assert_called_once_with(
            'show-controller', '--show-password', '--format', 'json')
