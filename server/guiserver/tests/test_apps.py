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

"""Tests for the Juju GUI server applications."""

import unittest

import mock

from guiserver import (
    apps,
    auth,
    handlers,
    manage,
)
from guiserver.bundles import base


class AppsTestMixin(object):
    """Base tests and helper methods for applications.

    Subclasses must define a get_app method returning the application.
    """

    def get_url_spec(self, app, pattern):
        """Return the app URL specification with the given regex pattern.

        Return None if the URL specification is not found.
        See tornado.web.URLSpec.
        """
        for spec in app.handlers[0][1]:
            if spec.regex.pattern == pattern:
                return spec
        return None

    def assert_in_spec(self, spec, key, value=None):
        """Ensure the given key-value pair is present in the specification.

        Also return the value in the specification.
        """
        self.assertIsNotNone(spec)
        self.assertIn(key, spec.kwargs)
        obtained = spec.kwargs[key]
        if value is not None:
            self.assertEqual(value, obtained)
        return obtained

    def test_debug_enabled(self):
        # Debug mode is enabled if options.debug is True.
        app = self.get_app(debug=True)
        self.assertTrue(app.settings['debug'])

    def test_debug_disabled(self):
        # Debug mode is disabled if options.debug is False.
        app = self.get_app(debug=False)
        self.assertFalse(app.settings['debug'])


class TestServer(AppsTestMixin, unittest.TestCase):

    def get_app(self, **kwargs):
        """Create and return the server application.

        Use the options provided in kwargs.
        """
        options_dict = {
            'apiurl': 'wss://example.com:17070',
            'apiversion': 'go',
            'gzip': True,
            'jujuguidebug': False,
            'jujuversion': '2.0.0',
            'sandbox': False,
            'charmstoreurl': 'https://api.jujucharms.com/charmstore/',
            'bundleservice_url': '',
        }
        options_dict.update(kwargs)
        options = mock.Mock(**options_dict)
        with mock.patch('guiserver.apps.options', options):
            return apps.server()

    def get_gui_config(self, app):
        """Return the GUI config as a dictionary, given an app object."""
        spec = self.get_url_spec(app, r'.*$')
        application = spec.kwargs['fallback'].wsgi_application.application
        return application.registry.settings

    def test_auth_backend(self):
        # The authentication backend instance is correctly passed to the
        # WebSocket handlers.
        app = self.get_app()
        expected = auth.get_backend(manage.DEFAULT_API_VERSION)
        # The auth backend is registered for the controller connection.
        spec = self.get_url_spec(app, r'^/ws/model-api(?:/.*)?$')
        auth_backend = self.assert_in_spec(spec, 'auth_backend')
        self.assertIsInstance(auth_backend, type(expected))
        # The auth backend is registered for the model connection.
        spec = self.get_url_spec(app, r'^/ws/controller-api(?:/.*)?$')
        auth_backend = self.assert_in_spec(spec, 'auth_backend')
        self.assertIsInstance(auth_backend, type(expected))

    def test_deployer(self):
        # The deployer instance is correctly passed to the WebSocket handler.
        app = self.get_app()
        spec = self.get_url_spec(app, r'^/ws/model-api(?:/.*)?$')
        deployer = self.assert_in_spec(spec, 'deployer')
        self.assertIsInstance(deployer, base.Deployer)

    def test_ws_templates_controller(self):
        # The WebSocket templates are properly passed to the WebSocket handler
        # managing connections to the controller.
        app = self.get_app()
        spec = self.get_url_spec(app, r'^/ws/controller-api(?:/.*)?$')
        source = self.assert_in_spec(spec, 'ws_source_template')
        self.assertEqual('/ws/controller-api/$server/$port', source)
        target = self.assert_in_spec(spec, 'ws_target_template')
        self.assertEqual('wss://{server}:{port}/api', target)

    def test_ws_templates_model(self):
        # The WebSocket templates are properly passed to the WebSocket handler
        # managing connections to the model.
        app = self.get_app()
        spec = self.get_url_spec(app, r'^/ws/model-api(?:/.*)?$')
        source = self.assert_in_spec(spec, 'ws_source_template')
        self.assertEqual('/ws/model-api/$server/$port/$uuid', source)
        target = self.assert_in_spec(spec, 'ws_target_template')
        self.assertEqual('wss://{server}:{port}/model/{uuid}/api', target)

    def test_ws_templates_pre2(self):
        # The WebSocket templates are properly passed to the WebSocket handler
        # and the correct target template is used for Juju 1.x.
        app = self.get_app(jujuversion='1.25.42')
        spec = self.get_url_spec(app, r'^/ws/model-api(?:/.*)?$')
        source = self.assert_in_spec(spec, 'ws_source_template')
        self.assertEqual('/ws/model-api/$server/$port/$uuid', source)
        target = self.assert_in_spec(spec, 'ws_target_template')
        self.assertEqual(
            'wss://{server}:{port}/environment/{uuid}/api', target)

    def test_tokens(self):
        # The tokens instance is correctly passed to the WebSocket handler.
        app = self.get_app()
        spec = self.get_url_spec(app, r'^/ws/controller-api(?:/.*)?$')
        tokens = self.assert_in_spec(spec, 'tokens')
        self.assertIsInstance(tokens, auth.AuthenticationTokenHandler)
        spec = self.get_url_spec(app, r'^/ws/model-api(?:/.*)?$')
        tokens = self.assert_in_spec(spec, 'tokens')
        self.assertIsInstance(tokens, auth.AuthenticationTokenHandler)

    def test_websocket_in_sandbox_mode(self):
        # The sandbox WebSocket handler is used if sandbox mode is enabled.
        app = self.get_app(sandbox=True)
        spec = self.get_url_spec(app, r'^/ws(?:/.*)?$')
        self.assertIsNotNone(spec)
        self.assertEqual(handlers.SandboxHandler, spec.handler_class)
        config = self.get_gui_config(app)
        self.assertTrue(config['jujugui.sandbox'])

    def test_proxy_excluded_in_sandbox_mode(self):
        # The juju-core HTTPS proxy is excluded if sandbox mode is enabled.
        app = self.get_app(sandbox=True)
        spec = self.get_url_spec(app, r'^/juju-core/(.*)$')
        self.assertIsNone(spec)

    def test_core_http_proxy(self):
        # The juju-core HTTPS proxy handler is properly set up.
        app = self.get_app()
        spec = self.get_url_spec(app, r'^/juju-core/(.*)$')
        self.assert_in_spec(
            spec, 'target_url', value='https://example.com:17070')

    def test_serving_gui_tests(self):
        # The server can be configured to serve GUI unit tests.
        app = self.get_app(testsroot='/my/tests/')
        spec = self.get_url_spec(app, r'^/test/(.*)$')
        self.assert_in_spec(spec, 'path', value='/my/tests/')

    def test_not_serving_gui_tests(self):
        # The server can be configured to avoid serving GUI unit tests.
        app = self.get_app(testsroot=None)
        spec = self.get_url_spec(app, r'^/test/(.*)$')
        self.assertIsNone(spec)

    def test_gui_options(self):
        # The Juju GUI WSGI application is properly configured.
        app = self.get_app()
        config = self.get_gui_config(app)
        self.assertEqual(
            'https://api.jujucharms.com/charmstore/',
            config['jujugui.charmstore_url'])
        self.assertEqual(
            apps.WEBSOCKET_CONTROLLER_SOURCE_TEMPLATE,
            config['jujugui.controllerSocketTemplate'])
        self.assertEqual(
            apps.WEBSOCKET_MODEL_SOURCE_TEMPLATE,
            config['jujugui.socketTemplate'])
        self.assertTrue(config['jujugui.combine'])
        self.assertFalse(config['jujugui.interactive_login'])
        self.assertFalse(config['jujugui.sandbox'])
        self.assertFalse(config['jujugui.raw'])
        self.assertEqual('', config['jujugui.base_url'])

    def test_gui_bundleservice_connection(self):
        # The server can be configured to connect the Juju GUI to a
        # bundleservice.
        bundleservice_url = 'https://1.2.3.4/bundleservice'
        app = self.get_app(bundleservice_url=bundleservice_url,
                           interactivelogin=True)
        config = self.get_gui_config(app)
        self.assertEqual(bundleservice_url,
                         config['jujugui.bundleservice_url'])
        self.assertTrue(config['jujugui.interactive_login'])

    def test_gui_debug_mode(self):
        # The server can be configured to serve the GUI in debug mode.
        app = self.get_app(jujuguidebug=True)
        config = self.get_gui_config(app)
        self.assertTrue(config['jujugui.raw'])


class TestRedirector(AppsTestMixin, unittest.TestCase):

    def get_app(self, **kwargs):
        """Create and return the server application.

        Use the options provided in kwargs.
        """
        options = mock.Mock(**kwargs)
        with mock.patch('guiserver.apps.options', options):
            return apps.redirector()

    def test_redirect_all(self):
        # Ensure all paths are handled by HttpsRedirectHandler.
        app = self.get_app()
        spec = self.get_url_spec(app, r'.*$')
        self.assertIsNotNone(spec)
        self.assertEqual(handlers.HttpsRedirectHandler, spec.handler_class)
