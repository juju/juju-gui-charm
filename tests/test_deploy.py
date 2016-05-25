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

"""Juju GUI deploy module tests."""

import os
import unittest

import mock

from deploy import juju_deploy


def contains(needle, haystack):
    """Does the sequence (haystack) contain the given subsequence (needle)?"""
    for i in range(len(haystack)-len(needle)+1):
        for j in range(len(needle)):
            if haystack[i+j] != needle[j]:
                break
        else:
            return True
    return False


REPO_PATH = '/tmp/repo/'


@mock.patch('tempfile.mkdtemp', mock.Mock(return_value=REPO_PATH))
class TestJujuDeploy(unittest.TestCase):

    unit_info = {'public-address': 'unit.example.com'}
    charm = 'test-charm'
    local_charm = 'local:trusty/{}'.format(charm)

    @mock.patch('deploy.juju')
    @mock.patch('deploy.wait_for_unit')
    def call_deploy(
            self, mock_wait_for_unit, mock_juju,
            service_name=None, options=None, force_machine=None,
            charm_source=None, series='xenial'):
        mock_wait_for_unit.return_value = self.unit_info
        if charm_source is None:
            expected_source = os.path.join(os.path.dirname(__file__), '..')
        else:
            expected_source = charm_source
        with mock.patch('deploy.rsync') as mock_rsync:
            unit_info = juju_deploy(
                self.charm, service_name=service_name, options=options,
                force_machine=force_machine, charm_source=charm_source,
                series=series)
        mock_rsync.assert_called_once_with(expected_source, REPO_PATH)
        # The unit address is correctly returned.
        self.assertEqual(self.unit_info, unit_info)
        self.assertEqual(1, mock_wait_for_unit.call_count)
        # Juju is called two times: deploy and expose.
        juju_calls = mock_juju.call_args_list
        self.assertEqual(2, len(juju_calls))
        # We expect a "juju expose" to have been called on the service.
        expected_expose_call = mock.call('expose', service_name or self.charm)
        deploy_call, expose_call = juju_calls
        self.assertEqual(expected_expose_call, expose_call)
        self.assertEqual(deploy_call[0][0], 'deploy')
        return deploy_call[0]

    def test_deployment(self):
        # The function deploys and exposes the given charm.
        command = self.call_deploy()
        self.assertEqual(
            ('deploy', '--series', 'xenial', REPO_PATH, self.charm),
            command)

    def test_options(self):
        # The function handles charm options.
        mock_config_file = mock.Mock()
        mock_config_file.name = '/tmp/config.yaml'
        with mock.patch('deploy.make_charm_config_file') as mock_callable:
            mock_callable.return_value = mock_config_file
            command = self.call_deploy(options={'foo': 'bar'})
        # Since options were provided to the deploy call, a config file was
        # created and passed to "juju deploy".
        self.assertTrue(contains(('--config', mock_config_file.name), command))

    def test_force_machine(self):
        # The function can deploy charms in a specified machine.
        command = self.call_deploy(force_machine=42)
        self.assertTrue(contains(('--to', '42'), command))

    def test_charm_source(self):
        # The function can deploy a charm from a specific source.
        charm_source = '/tmp/source/'
        self.call_deploy(charm_source=charm_source)

    def test_series(self):
        # The function can deploy a charm from a specific series.
        command = self.call_deploy(series='raring')
        self.assertTrue(contains(('--series', 'raring'), command))

    def test_no_service_name(self):
        # If the service name is not provided, the charm name is used.
        command = self.call_deploy()
        service_name = command[-1]
        self.assertEqual(self.charm, service_name)

    def test_service_name(self):
        # A customized service name can be provided and it is passed to Juju as
        # the last argument.
        command = self.call_deploy(service_name='my-service')
        service_name = command[-1]
        self.assertEqual('my-service', service_name)
