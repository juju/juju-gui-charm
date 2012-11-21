#!/usr/bin/env python2

import sys
import unittest


class PassingTest(unittest.TestCase):
    def test_addition(self):
        self.assertEqual(1+1, 2)


if __name__ == '__main__':
    sys.exit(unittest.main())
