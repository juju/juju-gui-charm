<!--
RELEASE_PROCESS.md
Copyright 2016 Canonical Ltd.
This work is licensed under the Creative Commons Attribution-Share Alike 3.0
Unported License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/3.0/ or send a letter to Creative
Commons, 171 Second Street, Suite 300, San Francisco, California, 94105, USA.
-->

# Juju GUI Charm Release Process #

## Updating the GUI ##

If the new release of the charm is to include a new version of Juju GUI then
that version should be released and tagged in the master branch of the GUI. It
is ill-advised that the charm is released with a novel, unreleased version of
the GUI.  If, however, that is the goal, ensure you follow the instructions in
the `juju-gui/RELEASE_PROCESS.rst` file.

## Work from a freshly fetched repo ##

    git clone --branch master git@github.com:juju/juju-gui-charm.git
    cd juju-gui-charm
    git merge origin/develop

## Packaging the GUI ##

To build a new jujugui tar.bz2 file and gather all of the current dependencies,
run:

    make package

Ensure that a `tar.bz2` file for the expected juju-gui release is in
`releases` and that `jujugui-deps` is full of wheels and a couple
of source packages.

If a new `tar.bz2` file is in releases, you'll need to add it to git and
remove the old one.  The same for new packages in `jujugui-deps`.  See the
note below about updating the charm for Ubuntu Precise. You will not commit
the changes seen while packaging for precise into git.

## Testing the charm ##

Ensure the newly packaged charm deploys and behaves. Ensure you can create a
new environment.

### Juju 1.25 ###
     export JUJU_DEV_FEATURE_FLAGS=jes
     juju bootstrap
     make deploy

### Juju 2 ###
     juju bootstrap <controller> <cloud> --upload-tools
     make deploy

## Get the charm publishing tools ##

You'll need the `charm` package from the juju/devel PPA:

    sudo add-apt-repository ppa:juju/devel
    sudo apt update
    sudo apt install charm

## The juju-gui charm versions in the charmstore ##

We have multiple versions of the juju-gui charm in the charmstore.

| Release | Intent / Audience | URL | CS reference |
| ------- | ----------------- | --- | ------------ |
| Alphas | Dev team testing only | https://jujucharms.com/u/yellow/juju-gui | cs:~yellow/juju-gui |
| Betas  | Wider testing. Only via Juju > 2.0 | hhttps://jujucharms.com/juju-gui/?channel=development | cs:juju-gui --channel development |
| Released | GA | https://jujucharms.com/juju-gui | cs:juju-gui |

The betas and released versions are owned by ~juju-gui-charmers.

Before the release of Juju v2.0 the betas will be of limited utility as they
can only be tested using Juju 1.26 alphas.

## Uploading an alpha version ##

Our alphas are development versions of the charm and are published to the
cs:~yellow namespace for thorough testing before making a more general
release.

Before uploading, check to see the currently available versions:

    charm show cs:~yellow/juju-gui id perm

Next, to upload the charm, go to the charm source directory and do:

    make clean
    charm push . cs:~yellow/juju-gui

The `charm push` command above will output the fully qualified URL of the
charm, for instance "cs:~yellow/juju-gui-42". Use that to publish the charm:

    charm publish cs:~yellow/juju-gui-42

And check the information to ensure it changed:

    charm show cs:~yellow/juju-gui id perm

## Uploading a beta version ##

Our betas are development versions of the charm and are published to the
"cs:~juju-gui-charmers" namespace for thorough testing before making it stable.

Before uploading, check to see the currently available versions:

    charm show cs:~juju-gui-charmers/juju-gui id perm published

Next, to upload and publish the charm, go to the charm source directory and do:

    make publish-development

Check the information to ensure it changed:

    charm show --channel development cs:~juju-gui-charmers/juju-gui id perm published

Done.
If you want to perform the same operation manually, do the following:

    make clean
    charm push . cs:~juju-gui-charmers/juju-gui

The `charm push` command above will output the fully qualified URL of the
charm, for instance "cs:~juju-gui-charmers/juju-gui-42". Use that to publish
the charm:

    charm publish --channel development cs:~juju-gui-charmers/juju-gui-42

And check the information to ensure it changed:

    charm show --channel development cs:~juju-gui-charmers/juju-gui id perm published

# QA Process #

Before publishing the new juju-gui charm to the stable channel, both manual and
automatic QA must be performed. Refer to the `QA.md` doc for details on doing
pre-release testing of the charm.

## Publishing the released version ##

Once the charm has been QAed and proved to be solid and reliable, make it
stable by executing the following command:

    make publish-stable

Assuming the current development charm has revision 42, the above can be also
done by manually running the charm command:

    charm publish cs:~juju-gui-charmers/juju-gui-42

Finally, check the information to ensure it changed:

    charm show cs:~juju-gui-charmers/juju-gui id perm published

## Tagging the charm code ##

The charm should be tagged, ideallly with a number based on the release
version of the Juju GUI. It should then be pushed back to github.

    git tag <semver>
    git push --tags origin master

## Releasing to Launchpad for production ##

When the charm is ready to be released to production, it must be packaged,
commited to github, QA'd, reviewed, and merged.

In order to push to Launchpad you need the following stanza in your
$HOME/.gitconfig.  Replace LPUSER with your Launchpad user id.

[url "ssh://LPUSER@git.launchpad.net/"]
	insteadOf = lp:

Then push to Launchpad using the following:

    git remote add lporigin lp:~yellow/canonical-theblues-charms/+git/juju-gui
    git push --tags lporigin master

## Supporting the GUI for precise ##

Due to vagaries with supporting precise, a separately packaged charm
for precise is required. On precise the use of Python wheels is not supported
so all of the packages in `jujugui-deps` will be tarballs, not wheels.  The
charm we have commited to version control is series newer than precise.
Because of that, you'll need to temporarily remove all of the wheels in
`jujugui-deps` before making the package for precise.  On a precise machine,
do the following:

    rm -rf jujugui-deps/*
    make package

Also modify the `metadata.yaml` file by removing the line starting with
"series: ".

At this point `jujugui-deps` should have no wheels, only gzipped tarballs.
After testing and QA, upload the fat charm to the charmstore with:

    charm push . cs:~yellow/precise/juju-gui
    charm push . cs:~juju-gui-charmers/precise/juju-gui

And then publish them with `charm publish` specifying the revisions.

At this point it is important that the packaging changes that were just made
are discarded so they are not accidentally committed to git.  Do the
following:

    git reset --hard HEAD~1
