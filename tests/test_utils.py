#!/usr/bin/env python2

import os
import sys
import tempfile
import unittest

from utils import render_to_file


class RenderToFileTest(unittest.TestCase):

    def setUp(self):
        self.destination_file = tempfile.NamedTemporaryFile()
        self.addCleanup(self.destination_file.close)
        self.template_contents = '%(foo)s, %(bar)s'
        with tempfile.NamedTemporaryFile(delete=False) as template_file:
            template_file.write(self.template_contents)
            self.template_path = template_file.name
        self.addCleanup(os.remove, self.template_path)

    def test_render_to_file(self):
        # Ensure the template is correctly rendered using the given context.
        context = {'foo': 'spam', 'bar': 'eggs'}
        render_to_file(self.template_path, context, self.destination_file.name)
        expected = self.template_contents % context
        self.assertEqual(expected, self.destination_file.read())


if __name__ == '__main__':
    sys.exit(unittest.main())
