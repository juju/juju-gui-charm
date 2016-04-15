<!--
QA.md
Copyright 2016 Canonical Ltd.
This work is licensed under the Creative Commons Attribution-Share Alike 3.0
Unported License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/3.0/ or send a letter to Creative
Commons, 171 Second Street, Suite 300, San Francisco, California, 94105, USA.
-->

# Juju GUI QA Process #

Before releasing the Juju GUI charm it needs to be thoroughly tested across a
large number of scenarios. This document is not exhaustive but lists the best
practice checklist for what should be an acceptable QA.

Given the large number of scenarios, expect this to take at least four
hours. Currently it is a manual process but we hope to partially automate it
soon.

## Various ways to launch the GUI ##

* Sandbox mode
  - In the juju-gui code, `make qa-server`

* Deployed via the charm using Juju v1.24
  - Test single model only.
  ```
  juju bootstrap
  make deploy
  ```

* Deployed via the charm using Juju v1.25

  Model only with controller.
    * No access to admin environment
    * Cannot create new model
  ```
  export JUJU_DEV_FEATURE_FLAGS=jes
  juju bootstrap
  make deploy
  ```

* Deployed via the charm using Juju v2.0 / 1.26alpha

  Ability to create new models
  ```
  export JUJU_DEV_FEATURE_FLAGS=jes
  juju bootstrap
  make deploy
  ```

* Embedded in Juju v2.0
  ```
  juju bootstrap --upload-tools lxd lxd
  juju gui
  ```

* JEM

  The details for this scenario need to be worked out. Basically:
    * Bootstrap an empty environment to an external provider, e.g. ec2
      * `juju bootstrap -e ec2`
    * Deploy the GUI charm locally:
      * `juju bootstrap -e local && make deploy`
    * ?? Deploy JEM somewhere?  Hook them up?

* Via the horizon-juju-charm (HJC)

  See the horizon-juju-charm `HACKING.md` file for instructions on how to
  embed the juju-gui into HJC and test it.

## Providers ##

All of the above tests need to be run on these providers:

* Amazon
* local
* lxd (time permitting)
* openstack on bastion[1] or canonistack
* Azure
  - Do not test with Juju 1.24
  - Juju 1.25 should allow model creation, pending GUI support.
  - Juju 2.0 will not allow model creation in the near term.

## Automated functional testing ##

The uitest project contains integration tests for many Juju services, including
the charmed GUI. The following steps describe how to set up and run the suite
against a juju-gui charm already pushed to the charm store in the development
channel as "cs:~juju-gui-charmers/juju-gui".

* Check out and build the uitest project:
  ```
  git clone git@github.com:CanonicalLtd/juju-uitest.git
  cd juju-uitest
  make sysdeps
  make
  ```

* Run the juju-gui charm tests.
  The command assumes the charm lives in ~/code/juju-gui-charm:
  ```
  devenv/bin/uitest -c lxd --gui-archive ~/code/juju-gui-charm/releases/*.bz2 TestGUIInCharm
  ```
  This will take a while, as it builds and compiles latest Juju master from
  scratch, bootstraps an lxd model, deploys the latest development juju-gui
  charm (modified to include the provided Juju GUI release archive) in it and
  then use it for running selenium tests.

For further information on command options, run `devenv/bin/uitest -h`.
Look at https://github.com/CanonicalLtd/juju-uitest/blob/master/README.md for
more information about uitest requirements and debugging practices.

## Manual testing steps ##

The goal is to launch a GUI in each of the _scenarios_ * _providers_.  Once it is
launched, the following tests should be performed, where applicable.

* Create a new model and switch to it.
* Deploy a bundle
* Create a relation
* Allocate machines and containers
* Deploy services on the new machines and containers
* Switch back and forth between models and ensure services, machines, and
  containers are where you put them.

[1] To access bastion, connect to the Canonical VPN and ssh to
10.245.163.113. The `trusty` environment is the one we are using.
