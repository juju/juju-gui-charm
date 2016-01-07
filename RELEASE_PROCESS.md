<!--
RELEASE.md
Copyright 2016 Canonical Ltd.
This work is licensed under the Creative Commons Attribution-Share Alike 3.0
Unported License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/3.0/ or send a letter to Creative
Commons, 171 Second Street, Suite 300, San Francisco, California, 94105, USA.
-->

# Juju GUI Charm Release Process #

## Updating the GUI ##

If the new charm release contains a new drop of the Juju GUI then before
releasing the charm the GUI should have its version bumped and committed to
the master branch.  Follow the instructions in the
`juju-gui/RELEASE_PROCESS.rst` file.  If the charm code is all that changed
then the GUI doesn't need to be updated.

## Packaging the GUI ##

In the juju-gui-charm branch you'll need to create the juju-gui package and
dependencies which can be done with:

    make package

Ensure that a tar.bz2 for the expected juju-gui release is in `releases` and
that `jujugui-deps` is full of dependency wheels and a couple of source
packages.

## Testing the charm ##

Ensure the newly packaged charm deploys and behaves. Ensure you can create a
new environment.

     export JUJU_DEV_FEATURE_FLAGS=jes
     juju bootstrap
     make deploy

## Get the charm publishing tools ##

You'll need the `charm` package from the private PPA at:
https://launchpad.net/~yellow/+archive/ubuntu/theblues

Follow the instructions to install the PPA at
https://launchpad.net/~/+archivesubscriptions

Then install the package with:

    sudo apt update
    sudo apt install charm

## Where the juju-gui charm versions live in the charmstore ##

We have multiple versions of the juju-gui charm in the charmstore.

| Release | Intent / Audience | URL | CS reference |
| Alphas | Dev team testing only | https://jujucharms.com/u/yellow/juju-gui | cs:~yellow/juju-gui |
| Betas  | Wider testing. Only via Juju 1.26 | https://jujucharms.com/development/juju-gui | cs:development/juju-gui |
| Released | GA | https://jujucharms.com/juju-gui | cs:juju-gui |

The betas and released versions are owned by ~juju-gui-charmers. (A bug
currently causes the beta to appear to be owned by ~charmers but it is not.)
Both are promulgated but the beta is not published.

Before the release of Juju v2.0 the betas will be of limited utility as they
can only be tested using Juju 1.26 alphas.


## Uploading a ~yellow development version ##

Our development versions of the charm are published to the cs:~yellow
namespace for thorough testing before making a more general release.

Before uploading, check to see the currently available version:

    charm info --include=id,perm cs:~yellow/juju-gui

Next, to upload the charm, go to the charm source directory and do:

    charm upload . cs:~yellow/juju-gui  (may need to specify the series)
    charm info --include=id,perm cs:~yellow/juju-gui

At this point the charm is in the development channel and is referenced as
`cs:~yellow/development/juju-gui`

## Publishing the charm alpha ##

To move the charm out of the development channel, publish it with:

    charm publish cs:~yellow/trusty/juju-gui  /!\ Is series required here?

## Uploading to beta ##

The procedure is the same but the beta is owned by ~juju-gui-charmers but it
is promulgated so you can publish directly to:

    charm upload . cs:development/juju-gui

## Publishing a beta becomes the released version ##

The released version of the charm is simply the promulgated development
version (the beta) after being published.  So upload the beta, do all of the
required testing, and then publish it to make the release:

    charm publish cs:development/juju-gui
