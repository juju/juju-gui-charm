<!--
HACKING.md
Copyright 2013 Canonical Ltd.
This work is licensed under the Creative Commons Attribution-Share Alike 3.0
Unported License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/3.0/ or send a letter to Creative
Commons, 171 Second Street, Suite 300, San Francisco, California, 94105, USA.
-->

# Juju GUI Charm Development #

## Contacting the Developers ##

Hi.  Thanks for looking at the charm.  If you are interested in helping us
develop, we'd love to hear from you.  Our developer-oriented discussions
happen on Freenode's IRC network in the #juju-gui channel, and you can also
join [the GUI developers mailing list](https://lists.ubuntu.com/mailman/listinfo/juju-gui).

## Getting Started ##

First, you need a configured Juju environment: see the Juju docs about
[getting started](https://juju.ubuntu.com/docs/getting-started.html). If you
do not yet have an environment defined, the Juju Quickstart plugin is an easy
way to get started. See https://pypi.python.org/pypi/juju-quickstart.

You'll also need some system dependencies and developer basics.

    make sysdeps

The command above will run as root and install the required deb packages.

Next, you need the bzr branch.  We work from
[lp:~juju-gui/charms/trusty/juju-gui/trunk](https://code.launchpad.net/~juju-gui/charms/trusty/juju-gui/trunk).

You could start hacking now, but there's a bit more to do to prepare for
running and writing tests.

We use the juju-test test command to run our functional and unit tests. It is
available as part of the charm tools package:

    sudo add-apt-repository ppa:juju/stable
    sudo apt-get update
    sudo apt-get install charm-tools

Before being able to run the suite, test requirements need to be installed
running the command:

    make

The command above will create a ".venv" directory inside "juju-gui/tests/",
ignored by version control, containing the development virtual environment with
all the testing dependencies.
Run "make help" to see all the available make targets.

## Testing ##

There are two types of tests for the charm: unit tests and functional tests.

Functional tests make use of a real Juju environment, and thus they need the
`~/.juju/environments.yaml` file to be properly configured, including the
`default-series` option. Since functional tests deploy the charm in the
bootstrap node, setting the default series also selects which series version
the charm will be deployed by functional tests. For instance, to test the Juju
GUI charm on trusty, set `default-series: trusty` in your
`~/.juju/environments.yaml` file. Possible values are `precise` and `trusty`.

Long story short, to run both unit and functional tests:

    make test JUJU_ENV="myenv"

In the command above, "myenv" is the juju environment, as it is specified in
your `~/.juju/environments.yaml`, that will be bootstrapped before running the
tests and destroyed at the end of the test run.

Note that the **functional tests will not work using an LXC environment**.
As mentioned, the test co-locates the juju-gui on the bootstrap node, which is
not possible in LXC.

Please read further for additional details.

### Unit Tests ###

The unit tests do not require a functional Juju environment, and can be run
with this command::

    make unittest

Unit tests should be created in the "tests" subdirectory and be named in the
customary way (i.e., "test_*.py").

### Functional Tests ###

Running the functional tests requires a Juju testing environment as provided
by the juju-test command (see "Getting Started", above).

To run only the functional tests:

    make ftest JUJU_ENV="myenv"

As seen before, "myenv" is the juju environment, as it is specified in your
`~/.juju/environments.yaml`, that will be bootstrapped before running the
tests and destroyed at the end of the test run.

## Running the Charm From Development ##

If you have set up your environment to run your local development charm,
deploying the charm fails if attempted after the testing virtualenv has been
created: juju deploy exits with an error due to ".venv" directory containing
an absolute symbolic link.  There are two ways to work around this problem.

The first one is running "make clean" before deploying the charm:

    make clean
    juju bootstrap
    juju deploy --repository=/path/to/charm/repo local:trusty/juju-gui
    juju expose juju-gui

The second one is just running "make deploy":

    juju bootstrap
    make deploy

The "make deploy" command creates a temporary Juju repository (excluding
the ".venv" directory), deploys the Juju GUI charm from that repository and
exposes the juju-gui service.  Also note that "make deploy" does not require
you to manually set up a local Juju environment, and preserves, if already
created, the testing virtualenv.

The `make deploy` command also supports specifying the OS version used to
deploy the local charm. By default a trusty machine is created, but you can
run the following to deploy the charm on precise:

    make deploy SERIES=precise

Now you are working with a test run, as described in
<https://juju.ubuntu.com/docs/write-charm.html#test-run>.  The
`juju debug-hooks` command, described in the same web page, is your most
powerful tool to debug.

When something goes wrong, on your local machine run
`juju debug-hooks juju-gui/0` or similar.  This will initially put you on the
unit that has the problem.  You can look at what is going on in
`/var/lib/juju/agents/[NAME OF UNIT]` (or instead of agents use `containers`
in the local environment. There is a charm.log file to investigate, and a 
charm directory which contains the charm.  The charm directory contains the 
`juju-gui` and `juju` directories, so everything you need is there.

If juju recognized an error (for instance, the unit is in an "install-error"
state) then you can do more.  In another terminal on your local machine, run
`juju resolved --retry`.  Then return to the debug-hooks terminal.  You will
see that your exploration work has been replaced, and you are simply in the
charms directory.  At the bottom of the terminal, you will see "install" as
part of the data that the debug-hooks machinery (via byobu) shows you.  You
are now responsible for running the install hook.  For instance, in this case,
you would run

    ./hooks/install

You can then watch what is going on.  If something goes wrong, fix it and try
it again.  Juju will not treat the hook as complete until you end the session
(e.g. CTRL-D).  At that point, Juju will treat the hook as successful, and
move on to the next stage.  Since you are in debug-hooks mode still, you will
be responsible for running that hook too!  Look at the bottom of the terminal
to see what hook you are supposed to run.

All of this is described in more detail on the Juju site: this is an
introduction to the process.

## Making charm releases ##

The same code base is used for both precise and trusty releases.
Releasing the charm is done by pushing changes from the development branch to
the precise and trusty release branches.
The branches live in the following locations:

- development branch: `lp:~juju-gui/charms/trusty/juju-gui/trunk`
- precise release: `lp:charms/juju-gui`
- trusty release: `lp:charms/trusty/juju-gui`

## Upgrading the local releases repository ##

The charm, in the default juju-gui-source configuration ("local"), deploys the
GUI from the local releases repository. The repository is the `releases`
directory located in the branch source, and contains GUI releases as tarball
files. When a new GUI version is released, we want to also update the local
repository. To do that, just copy the GUI tarball file to the `releases`
directory, and commit a new revision of the charm.
It is safe to remove the older files, and it is even recommended: too many
releases can slow down the deployment process, especially when deploying from
the local charm.
Note that at least one release must be always present in the repository,
otherwise the deployment process will fail.

## Upgrading the builtin server dependencies ##

The builtin server dependencies are stored in the `deps` directory located in
the branch source. This way, when the charm is deployed, the builtin server can
be set up without downloading dependencies from the network (pypi) and so the
charm deployment succeeds also behind a firewall.
To upgrade the dependencies, add a tarball to the `deps` directory, remove the
old dependency if required, and update the `server-requirements.pip` file.
At this point, running `make` should also update the virtualenv used for tests.

## Upgrading the test dependencies ##

The tests also have a number of dependencies.  For speed and reliability, these
are also in a directory.  However, they are not necessary for normal use of the
charm, and so, unlike the server dependencies, they are not part of the normal
charm branch.  The 00-setup script makes a lightweight checkout of the branch
lp:~juju-gui-charmers/juju-gui/charm-download-cache and then uses this to build
the test virtual environment.

To take best advantage of this approach, either use the same charm branch
repeatedly for development; or develop the charm within a parent directory
in which you have run `bzr init-repo`, so that the different branches can use
the local cache; or both.

To upgrade test dependencies, add them to the `test-requirements.pip` file and
add the tarballs to the download-cache branch.  You may need to temporarily
disable the `--no-allow-external` and `--no-index` flags in 00-setup to get
new transitive dependencies.  Once you do, run `pip freeze` to add the
transitive dependencies to the `test-requirements.pip` file, and make sure to
add those tarballs to the download cache as well.

## Builtin server bundle support ##

The builtin server starts/schedules bundle deployment processes when it
receives Deployer Import API requests. The user can then observe the deployment
progress using the GUI. The builtin server also exposes the possibility to
watch a bundle deployment progress: see `server/guiserver/bundles/__init__.py`
for a detailed description of the API request/response process.

Under the hood, the builtin server leverages the juju-deployer library in order
to import a bundle. Since juju-deployer is not asynchronous, the actual
deployment is executed in a separate process.

### Debugging bundle support ###

Sometimes, when an error occurs during bundle deployments, it is not obvious
where to retrieve information about what is going on.
The GUI builtin server exposes some bundle information in two places:

- https://<juju-gui-url>/gui-server-info displays in JSON format the current
  status of all scheduled/started/completed bundle deployments;
- /var/log/upstart/guiserver.log is the builtin server log file, which includes
  logs output from the juju-deployer library.

Moreover, setting `builtin-server-logging=debug` gives more debugging
information, e.g. it prints to the log the contents of the WebSocket messages
sent by the client (usually the Juju GUI) and by the Juju API server.
As mentioned, juju-deployer works on its own sandbox and uses its own API
connections, and for this reason the WebSocket traffic it generates is not
logged.

Sometimes, while debugging, it is convenient to restart the builtin server
(which also empties the bundle deployments queue). To do that, run the
following in the Juju GUI machine:

    service guiserver restart
