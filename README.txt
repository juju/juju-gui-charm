==============
Juju GUI Charm
==============

This charm makes it easy to deploy a Juju GUI into an existing environment.


Deploying the Juju GUI
======================

Deploying the Juju GUI is obviously accomplished using Juju itself.

You need a configured Juju environment: see the Juju docs about
`getting started <https://juju.ubuntu.com/docs/getting-started.html>`_).

Then you need to link this checkout of the Juju GUI charm from within the
charm repository::

  $ ln -s /path/to/charm/checkout/ /path/to/charm/repo/juju-gui

Deploying parameters may be configured by creating a configuration file in
YAML format. A synopsis of the available options is found in ``config.yaml``.

Finally, run the following commands::

  $ juju bootstrap
  $ juju deploy --config config.yaml juju-gui
  $ juju expose

It will take a while, run ``juju status`` until the unit machine is active.
The Juju GUI will then be accessible at <http://unit-machine-name/>.
