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

"""Tests for the bundle deployment base objects."""

from contextlib import contextmanager
import threading

import mock
from tornado import (
    concurrent,
    gen,
)
from tornado.testing import(
    AsyncTestCase,
    gen_test,
)

from guiserver import auth
from guiserver.bundles import (
    base,
    blocking,
    utils,
)


class ThreadCheckMock(object):
    """Help ensuring that a mock function is called in a separate thread."""

    thread_name = None

    def __call__(self, *args, **kwargs):
        self.thread_name = self.get_thread_name()

    def get_thread_name(self, *args, **kwargs):
        """Return the name of the current thread."""
        return threading.current_thread().name

    def assert_called_in_a_separate_thread(self):
        """Ensure this object was called in a separate thread."""
        msg = 'called in the same thread: {}'.format(self.thread_name)
        assert self.thread_name != self.get_thread_name(), msg


@mock.patch('time.time', mock.Mock(return_value=42))
class TestDeployer(AsyncTestCase):

    apiurl = 'wss://api.example.com:17070'
    bundle = {'foo': 'bar'}
    user = auth.User(
        username='myuser', password='mypasswd', is_authenticated=True)

    def make_deployer(self, apiversion=None):
        """Create and return a Deployer instance."""
        if apiversion is None:
            apiversion = base.SUPPORTED_API_VERSIONS[0]
        return base.Deployer(self.apiurl, apiversion)

    @contextmanager
    def patch_executor(self):
        future = concurrent.Future()
        executor_path = 'guiserver.bundles.base.ThreadPoolExecutor'
        mock_executor = mock.Mock()
        mock_executor.submit.return_value = future
        with mock.patch(executor_path, mock_executor):
            yield future

    @gen.coroutine
    def consume_changes(self, deployer, deployment_id):
        watcher_id = deployer.watch(deployment_id)
        all_changes = []
        while True:
            changes = yield deployer.next(watcher_id)
            all_changes.extend(changes)
            if changes[-1]['Status'] == utils.COMPLETED:
                break
        raise gen.Return(all_changes)

    @gen_test
    def test_validation_success(self):
        # A None Future is returned if the bundle validates.
        deployer = self.make_deployer()
        validate_path = 'guiserver.bundles.blocking.validate'
        with mock.patch(validate_path) as mock_validate:
            result = yield deployer.validate(self.user, 'bundle', self.bundle)
        self.assertIsNone(result)
        mock_validate.assert_called_once_with(
            self.apiurl, self.user.password, self.bundle)

    @gen_test
    def test_validation_process(self):
        # The validation is executed in a separate thread.
        deployer = self.make_deployer()
        mock_validate = ThreadCheckMock()
        with mock.patch('guiserver.bundles.blocking.validate', mock_validate):
            yield deployer.validate(self.user, 'bundle', self.bundle)
        mock_validate.assert_called_in_a_separate_thread()

    @gen_test
    def test_validation_failure(self):
        # An error message is returned if the validation fails.
        deployer = self.make_deployer()
        mock_validate = mock.Mock(side_effect=ValueError('validation error'))
        with mock.patch('guiserver.bundles.blocking.validate', mock_validate):
            result = yield deployer.validate(self.user, 'bundle', self.bundle)
        self.assertEqual('validation error', result)

    @gen_test
    def test_unsupported_api_version(self):
        # An error message is returned the API version is not supported.
        deployer = self.make_deployer(apiversion='not-supported')
        result = yield deployer.validate(self.user, 'bundle', self.bundle)
        self.assertEqual('unsupported API version', result)

    def test_watch(self):
        # To start observing a deployment progress, a client can obtain a
        # watcher id for the given deployment job.
        deployer = self.make_deployer()
        with mock.patch('guiserver.bundles.blocking.import_bundle'):
            deployment_id = deployer.import_bundle(
                self.user, 'bundle', self.bundle)
        self.assertIsInstance(deployer.watch(deployment_id), int)
        import pdb; pdb.set_trace()
        self.io_loop.close()

    def test_watch_unknown_deployment(self):
        # None is returned if a client ask to observe an invalid deployment.
        deployer = self.make_deployer()
        self.assertIsNone(deployer.watch(42))

    # @gen_test
    # def test_next(self):
    #     # A client can be asynchronously notified of deployment changes.
    #     deployer = self.make_deployer()
    #     with mock.patch('guiserver.bundles.blocking.import_bundle'):
    #         deployment_id = deployer.import_bundle(
    #             self.user, 'bundle', self.bundle)
    #     changes = yield self.consume_changes(deployer, deployment_id)
    #     print changes


    # def test_bundle_scheduling(self):
    #     # A deployment id is returned if the bundle import process is
    #     # successfully scheduled.
    #     deployer = self.make_deployer()
    #     import_bundle_path = 'guiserver.bundles.blocking.import_bundle'
    #     with mock.patch(import_bundle_path) as mock_import_bundle:
    #         result = deployer.import_bundle(self.user, 'bundle', self.bundle)
    #     self.assertIsInstance(result, int)
    #     mock_import_bundle.assert_called_once_with(
    #         self.apiurl, self.user.password, 'bundle', self.bundle)





    # @gen_test
    # def test_import_bundle_process(self):
    #     # The import bundle process is executed in a separate thread.
    #     deployer = self.make_deployer()
    #     mock_validate = ThreadCheckMock()
    #     with mock.patch('guiserver.bundles.blocking.validate', mock_validate):
    #         yield deployer.validate(self.user, 'bundle', self.bundle)
    #     mock_validate.assert_called_in_a_separate_thread()

    # def test_multiple_bundle_scheduling(self):
    #     pass


    # @gen_test
    # def test_run_process(self):
    #     # The run executor is correctly used.
    #     executor_path = 'guiserver.bundles.Deployer._run_executor'
    #     with mock.patch(executor_path) as mock_executor:
    #         deployer = self.make_deployer()
    #         yield deployer.run(self.user, 'bundle', self.bundle)
    #     mock_executor.submit.assert_called_once_with(
    #         bundles._import, self.apiurl, self.user.password, 'bundle',
    #         self.bundle)

    # @gen_test
    # def test_run_failure(self):
    #     # An error message is returned if the bundles deployment raises an
    #     # error.
    #     deployer = self.make_deployer()
    #     mock_import = self.make_pickleable_mock(error='import error')
    #     with mock.patch('guiserver.bundles._import', mock_import):
    #         result = yield deployer.run(self.user, 'bundle', self.bundle)
    #     self.assertEqual('import error', result)

    # @gen_test
    # def test_queue(self):
    #     # The queue attribute is correctly increased/decreased.
    #     deployer = self.make_deployer()
    #     mock_import = self.make_pickleable_mock()
    #     with mock.patch('guiserver.bundles._import', mock_import):
    #         self.assertEqual(0, deployer.queue)
    #         future1 = deployer.run(self.user, 'bundle1', self.bundle)
    #         future2 = deployer.run(self.user, 'bundle2', self.bundle)
    #         self.assertEqual(2, deployer.queue)
    #         yield future1
    #         yield future2
    #         self.assertEqual(0, deployer.queue)
