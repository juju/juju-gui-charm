"""Juju GUI deploy module tests."""

import unittest

import mock

from deploy import juju_deploy


class TestJujuDeploy(unittest.TestCase):

    address = 'unit.example.com'
    charm = 'test-charm'
    env = 'test-env'
    expose_call = mock.call('expose', '-e', env, charm)
    local_charm = 'local:{}'.format(charm)
    repo = '/tmp/repo/'

    @mock.patch('deploy.juju')
    @mock.patch('deploy.wait_for_service')
    @mock.patch('deploy.setup_repository')
    def call_deploy(
            self, mock_setup_repository, mock_wait_for_service, mock_juju,
            **kwargs):
        mock_setup_repository.return_value = self.repo
        mock_wait_for_service.return_value = self.address
        with mock.patch('deploy.jujuenv', self.env):
            address = juju_deploy(self.charm, **kwargs)
        # The unit address is correctly returned.
        self.assertEqual(self.address, address)
        self.assertEqual(1, mock_wait_for_service.call_count)
        # Juju is called two times: deploy and expose.
        juju_calls = mock_juju.call_args_list
        self.assertEqual(2, len(juju_calls))
        deploy_call, expose_call = juju_calls
        self.assertEqual(self.expose_call, expose_call)
        return deploy_call
        # # The juju deploy call takes no kwargs.
        # deploy_args, deploy_kwargs = deploy_call
        # self.assertEqual({}, deploy_kwargs)
        # # Check the expose call and return the deploy call args.
        # self.assertEqual(self.expose_call, expose_call)
        # return deploy_args

    def test_deployment(self):
        # The function deploys and exposes the given charm.
        expected_deploy_call = mock.call(
            'deploy',
            '-e', self.env,
            '--repository', self.repo,
            self.local_charm,
        )
        deploy_call = self.call_deploy()
        self.assertEqual(expected_deploy_call, deploy_call)

    def test_options(self):
        # The function handles charm options.
        mock_config_file = mock.Mock()
        mock_config_file.name = '/tmp/config.yaml'
        expected_deploy_call = mock.call(
            'deploy',
            '-e', self.env,
            '--repository', self.repo,
            '--config', mock_config_file.name,
            self.local_charm,
        )
        with mock.patch('deploy.make_charm_config_file') as mock_callable:
            mock_callable.return_value = mock_config_file
            deploy_call = self.call_deploy(options={'foo': 'bar'})
        self.assertEqual(expected_deploy_call, deploy_call)

    def test_force_machine(self):
        # The function can deploy services in a specified machine.
        expected_deploy_call = mock.call(
            'deploy',
            '-e', self.env,
            '--repository', self.repo,
            '--force-machine', '42',
            self.local_charm,
        )
        deploy_call = self.call_deploy(force_machine=42)
        self.assertEqual(expected_deploy_call, deploy_call)
