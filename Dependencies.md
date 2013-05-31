# Juju GUI Charm external dependencies #

The Juju GUI has a number of external dependencies including packages that are
in the Ubuntu repositories and other packages that are collected together into
a single PPA that the Juju GUI charm developers maintain.

The packages in our devel PPA provide a superset of all software the charm may
need for different deployment strategies, such as using the sandbox
vs. improv, or Python Juju vs. Go Juju.

# Stable and Devel #

The GUI developers are members of the group ~juju-gui on Launchpad
(http://launchpad.net/~juju-gui). We have two PPAs hosted there to support the
GUI, `stable` and `devel`.

To isolate charm deployments from upstream code changes, we have collected all
of the external software we depend upon and stored them in the PPAs we manage.

The `stable` PPA includes only versions of our dependencies that we have
tested and found to work with the charm.  The `devel` version includes new
versions of external software that are in the process of being tested.

# Selecting the PPA #

In the charm configuration file (config.yaml) there is an entry `gui_ppa` that
defaults to `juju-gui/charm_stable`.  You can change that in your config.yaml
file or do a `juju set juju-gui ppa_version=juju-gui/charm_devel`, for
instance, immediately after deploying the GUI charm to pull from the devel
version.  Only Juju GUI developers doing QA for the new PPA should ever need
to select the devel version.

# Deploying for the enterprise #

Organizations deploying the charm for their enterprise may have the
requirement to not allow the installation of software from outside of their
local network.  Typically those environments require all external software to
be downloaded to a local server and used from there.  Our devel PPA provides a
single starting place to obtain QA'd software.  Dev ops can grab the subset of
packages they need, audit, test, and then server them locally.

# List of dependencies #

Source				Package			Use	version / repo
----------------------------	----------------	---	----------
ppa:chris-lea/node.js-legacy	nodejs	 		base	0.8.23-1chl1~precise1
				npm			base	1.2.18-1chl1~precise1

ppa:juju-gui/ppa		haproxy			gui	1.5-dev17-1

ppa:juju/pkgs			python-charmhelpers	base	0.3+bzr178-3~precise1 (deprecated)
				python-shelltoolbox[1]	base	0.2.1+bzr17-1~precise1~ppa1

ubuntu repositories		python-yaml		go	3.10-2 / main
				python-apt		base	0.8.3ubuntu7.1 / main
				python-launchpadlib	base	1.9.12-1 / main
				python-tempita		base	0.5.1-1build1 / main
				zookeeper		improv	3.3.5+dfsg1-1ubuntu1 / universe

[1] The version of python-shelltoolbox in universe is 0.2.1+bzr17-1.  There is
probably no reason it cannot be pulled from there rather than ppa:juju/pkgs.

