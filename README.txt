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

At the time of this writing the Jitsu test command is not yet released.  To run
it you must first install it locally.  The files may be installed globally, or
into your home directory (as here)::

    sudo apt-get install autoconf libtool python-charmhelpers
    bzr branch lp:~jimbaker/juju-jitsu/unit-test jitsu-unit-test
    cd jitsu-unit-test
    autoreconf
    ./configure --prefix=$HOME
    make
    make install

The current incarnation of the Jitsu test command requires that the current
directory name match the charm name, so you must check out the charm into a
directory named "juju-gui"::

    bzr branch lp:~juju-gui/charms/precise/juju-gui/trunk juju-gui

The branch directory must be placed (or linked from) within a local charm
repository. It consists of a directory, itself containing a number of
directories, one for each distribution codename, e.g. ``precise``. In turn, the
codename directories will contain the charm repositories.

Now you are ready to run the functional tests (see the next section).


Running the functional tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Jitsu requires the charm directory be named the same as the charm and it be the
current working directory when the tests are run::

    JUJU_REPOSITORY=/path/to/charm/repo ~/bin/jitsu test juju-gui \
        --logdir /tmp --timeout 40m

If you are going to run the tests often, you probably want to set up LXC and
run the tests locally by setting your default environment to a "local" one.
Among other things you will need to install apt-cacher-ng and LXC to do so.

Unfortunately, currently running tests on a local environment is quite slow
(with quantal host and precise container at least), so you may want to further
increase the ``jitsu test`` command timeout.

If Jitsu generates errors about not being able bootstrap::

    CalledProcessError: Command '['juju', 'bootstrap']'...

...or it hangs, then you may need to bootstrap the environment yourself and
pass the --no-bootstrap switch to Jitsu.

If you do not yet have an environment defined, the Jitsu command
"setup-environment" is an easy way to get started.
