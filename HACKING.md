# Juju GUI Charm Development #

## Contacting the Developers ##

Hi.  Thanks for looking at the charm.  If you are interested in helping us
develop, we'd love to hear from you.  Our developer-oriented discussions
happen on freenode's IRC network in the #juju-gui channel, and you can also
join [the GUI developers mailing list](https://lists.ubuntu.com/mailman/listinfo/juju-gui).


## Getting Started ##

First, you need a configured Juju environment: see the Juju docs about
[getting started](https://juju.ubuntu.com/docs/getting-started.html). If you
do not yet have an environment defined, the Jitsu command "setup-environment"
is an easy way to get started.

You'll also need some dependencies and developer basics.

    sudo apt-get install bzr autoconf libtool python-charmhelpers

Next, you need the bzr branch.  We work from
[lp:~juju-gui/charms/precise/juju-gui/trunk](https://code.launchpad.net/~juju-gui/charms/precise/juju-gui/trunk).

You could start hacking now, but there's a bit more to do to prepare for
running and writing tests.

We use the Jitsu test command to run our functional tests.  At the time of
this writing it is not yet released.  To run it you must first install it
locally.  The files may be installed globally, or into your home directory (as
here):

    sudo apt-get install autoconf libtool python-charmhelpers python-selenium
    bzr branch lp:~jimbaker/juju-jitsu/unit-test jitsu-unit-test
    cd jitsu-unit-test
    autoreconf
    ./configure --prefix=$HOME
    make
    make install

The current incarnation of the Jitsu test command requires that the current
directory name match the charm name, so you must check out the charm into a
directory named "juju-gui":

    bzr branch lp:~juju-gui/charms/precise/juju-gui/trunk juju-gui

The branch directory must be placed (or linked from) within a local charm
repository. It consists of a directory, itself containing a number of
directories, one for each distribution codename, e.g. `precise`. In turn, the
codename directories will contain the charm directories. Therefore, you
should put your charm in a path like this: `[REPO]/precise/juju-gui`.

Now you are ready to run the functional tests (see the next section).

## Testing ##

There are two types of tests for the charm: unit tests and functional tests.


### Unit Tests ###

The unit tests do not require a functional Juju environment, and can be run
with this command::

    python tests/unit.test

Unit tests should be created in the "tests" subdirectory and be named in the
customary way (i.e., "test_*.py").


### Functional Tests ###

Running the functional tests requires a Juju testing environment as provided
by the Jitsu test command (see "Getting Started", above).  All files in the
tests directory which end with ".test" will be run in a Juju Jitsu test
environment.

Jitsu requires the charm directory to be named the same as the charm and to be
the current working directory when the tests are run::

    JUJU_REPOSITORY=/path/to/charm/repo ~/bin/jitsu test juju-gui \
        --logdir /tmp --timeout 40m

This command will bootstrap the default Juju environment specified in your
`~/.juju/environments.yaml`.

#### LXC ####

Unfortunately, we have not found LXC-based Juju environments to be reliable
for these tests.  At this time, we recommend using other environments, such as
OpenStack; but we will periodically check the tests in LXC environments
because it would be great to be able to use it.  If you do want to use LXC,
you will need to install the apt-cacher-ng and lxc packages.

Currently running tests on a local environment is quite slow (with quantal
host and precise container at least), so you may want to further increase the
`jitsu test` command timeout.

If Jitsu generates errors about not being able to bootstrap...

    CalledProcessError: Command '['juju', 'bootstrap']'...

...or if it hangs, then you may need to bootstrap the environment yourself and
pass the --no-bootstrap switch to Jitsu.

## Running the Charm From Development ##

If you have set up your environment to run functional tests, you also have set
it up to run your local development charm.  Developing and debugging with this
is much easier than trying to develop and debug with the tests, unfortunately.

To get started, first, simply do a `juju bootstrap`.  Using a non-LXC
environment probably will reduce frustrations.  Then, deploy your charm like
this (again, assuming you have set up your repo the way the functional tests
need them, as described above).

    juju deploy --repository=/path/to/charm/repo --upgrade local:precise/juju-gui
    juju expose juju-gui

Now you are working with a test run, as described in
https://juju.ubuntu.com/docs/write-charm.html#test-run .  The
`juju debug-hooks` command, described in the same web page, is by far your
most powerful tool to debug.

When something goes wrong, on your local machine run
`juju debug-hooks juju-gui/0` or similar.  This will initially put you on the
unit that has the problem.  You can look at what is going on in
/var/lib/juju/units/[NAME OF UNIT].  There is a charm.log file to investigate,
and a charm directory which contains the charm.  The charm directory contains
the juju-gui and juju directories, so everything you need is there.

If juju recognized an error (for instance, the unit is in an "install-error"
state) then you can do more.  In another terminal on your local machine, run
`juju resolved --retry`.  Then return to the debug-hooks terminal.  You will
see that your exploration work has been replaced, and you are simply in the
charms directory.  At the bottom of the terminal, you will see "install" as
part of the data that the debug-hooks machinery (via byobu) shows you.  You
are now responsible for running the install hook.  For instance, in this case,
you would run

    $ ./hooks/install

You can then watch what is going on.  If something goes wrong, fix it and try
it again.  Juju will not treat the hook as complete until you end the session
(e.g. CTRL-D).  At that point, Juju will treat the hook as successful, and
move on to the next stage.  Since you are in debug-hooks mode still, you will
be responsible for running that hook too!  Look at the bottom of the terminal
to see what hook you are supposed to run.

All of this is described in more detail on the Juju site: this is an
introduction to the process.
