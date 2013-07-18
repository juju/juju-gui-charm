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

"""Tests for the Juju GUI server management helpers."""

from contextlib import contextmanager
import logging
import unittest

import mock

from guiserver import manage


@mock.patch('guiserver.manage.options')
class TestAddDebug(unittest.TestCase):

    def test_debug_enabled(self, mock_options):
        # The debug option is true if the log level is debug.
        logger = mock.Mock(level=logging.DEBUG)
        manage._add_debug(logger)
        mock_options.define.assert_called_once_with('debug', default=True)

    def test_debug_disabled(self, mock_options):
        # The debug option is false if the log level is not debug.
        logger = mock.Mock(level=logging.INFO)
        manage._add_debug(logger)
        mock_options.define.assert_called_once_with('debug', default=False)


class TestValidateRequired(unittest.TestCase):

    @contextmanager
    def assert_sysexit(self, option):
        """Ensure the code in the context manager block produces a system exit.

        Also check that the given error refers to the given option.
        """
        expected_error = 'error: the {} argument is required'.format(option)
        with mock.patch('sys.exit') as mock_exit:
            yield
            mock_exit.assert_called_once_with(expected_error)

    def test_success(self):
        # The validation passes if the args are correctly found.
        with mock.patch('guiserver.manage.options', {'arg1': 'value1'}):
            manage._validate_required('arg1')

    def test_success_multiple_args(self):
        options = {'arg1': 'value1', 'arg2': 'value2'}
        with mock.patch('guiserver.manage.options', options):
            manage._validate_required(*options.keys())

    def test_failure(self):
        with mock.patch('guiserver.manage.options', {'arg1': ''}):
            with self.assert_sysexit('arg1'):
                manage._validate_required('arg1')

    def test_failure_multiple_args(self):
        options = {'arg1': 'value1', 'arg2': ''}
        with mock.patch('guiserver.manage.options', options):
            with self.assert_sysexit('arg2'):
                manage._validate_required(*options.keys())

    def test_failure_missing(self):
        with mock.patch('guiserver.manage.options', {'arg1': None}):
            with self.assert_sysexit('arg1'):
                manage._validate_required('arg1')

    def test_failure_empty(self):
        with mock.patch('guiserver.manage.options', {'arg1': ' '}):
            with self.assert_sysexit('arg1'):
                manage._validate_required('arg1')

    def test_failure_invalid_type(self):
        with mock.patch('guiserver.manage.options', {'arg1': 42}):
            with self.assert_sysexit('arg1'):
                manage._validate_required('arg1')
