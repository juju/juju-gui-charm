==============
Juju GUI Charm
==============

This charm makes it easy to deploy a Juju GUI into an existing environment.


Testing
=======

There are two types of tests for the charm: unit tests and functional tests.


Unit tests
----------

The unit tests do not require a functional Juju environment, and can be run
with this command::

    python tests/unit.test

Unit tests should be created in the "tests" subdirectory and be named in the
customary way (i.e., "test_*.py").


Functional tests
----------------

Running the functional tests requires a Juju testing environment as provided
by the Jitsu test command.  All files in the tests directory which end with
".test" will be run in a Juju Jitsu test environment.


Functional test setup
~~~~~~~~~~~~~~~~~~~~~

At the time of this writing the Jitsu test command is not yet released.  To
run it you must first install it locally (replace USER with your user name)::

    sudo apt-get install autoconf libtool python-shelltoolbox
    bzr branch lp:~jimbaker/juju-jitsu/unit-test jitsu-unit-test
    cd jitsu-unit-test
    autoreconf
    ./configure --prefix=/home/USER
    make
    make install

The current incarnation of the Jitsu test command requires that the current
directory name match the charm name, so you must check out the charm into a
directory named "juju-gui"::

    bzr branch lp:~juju-gui/charms/precise/juju-gui/trunk juju-gui

Now you are ready to run the functional tests (see the next section).


Running the functional tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run the functional tests thusly::

    JUJU_REPOSITORY=/path/to/local/repo ~/bin/jitsu test juju-gui --logdir /tmp

If Jitsu generates errors about not being able bootstrap::

    CalledProcessError: Command '['juju', 'bootstrap']'...

...or it hangs, then you may need to bootstrap the environment yourself and
pass the --no-bootstrap switch to Jitsu.

If you do not yet have an environment defined, the Jitsu command
"setup-environment" is an easy way to get started.
