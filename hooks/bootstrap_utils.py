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

"""
These are actually maintained in python-shelltoolbox.  Precise does not have
that package, so we need to bootstrap the process by copying the functions
we need here.
"""

import subprocess


try:
    import shelltoolbox
except ImportError:

    def run(*args, **kwargs):
        """Run the command with the given arguments.

        The first argument is the path to the command to run.
        Subsequent arguments are command-line arguments to be passed.

        This function accepts all optional keyword arguments accepted by
        `subprocess.Popen`.
        """
        args = [i for i in args if i is not None]
        pipe = subprocess.PIPE
        process = subprocess.Popen(
            args, stdout=kwargs.pop('stdout', pipe),
            stderr=kwargs.pop('stderr', pipe),
            close_fds=kwargs.pop('close_fds', True), **kwargs)
        stdout, stderr = process.communicate()
        if process.returncode:
            exception = subprocess.CalledProcessError(
                process.returncode, repr(args))
            # The output argument of `CalledProcessError` was introduced in
            # Python 2.7. Monkey patch the output here to avoid TypeErrors
            # in older versions of Python, still preserving the output in
            # Python 2.7.
            exception.output = ''.join(filter(None, [stdout, stderr]))
            raise exception
        return stdout

else:
    run = shelltoolbox.run
