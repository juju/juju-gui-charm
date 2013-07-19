<!--
README.md
Copyright 2013 Canonical Ltd.
This work is licensed under the Creative Commons Attribution-Share Alike 3.0
Unported License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/3.0/ or send a letter to Creative
Commons, 171 Second Street, Suite 300, San Francisco, California, 94105, USA.
-->

# Juju GUI Charm #

This charm makes it easy to deploy a Juju GUI into an existing environment.

## Supported Browsers ##

The Juju GUI supports recent releases of the Chrome, Chromium and Firefox web
browsers.

## Demo/Staging Server ##

A [demo/staging server](http://uistage.jujucharms.com:8080/) is available.

## Deploying the Juju GUI ##

Deploying the Juju GUI is accomplished using Juju itself.

You need a configured and bootstrapped Juju environment: see the Juju docs
about [getting started](https://juju.ubuntu.com/docs/getting-started.html),
and then run the usual bootstrap command.

    juju bootstrap

Next, you simply need to deploy the charm and expose it.  (See also "Deploying
with Jitsu" below, for another option.)

    juju deploy juju-gui
    juju expose juju-gui

Finally, you need to identify the GUI's URL. It can take a few minutes for the
GUI to be built and to start; this command will let you see when it is ready
to go by giving you regular status updates:

    watch juju status

Eventually, at the end of the status you will see something that looks like
this:

    services:
      juju-gui:
        charm: cs:precise/juju-gui-7
        exposed: true
        relations: {}
        units:
          juju-gui/0:
            agent-state: started
            machine: 1
            open-ports:
            - 80/tcp
            - 443/tcp
            public-address: ec2-www-xxx-yyy-zzz.compute-1.amazonaws.com

That means you can go to the public-address in my browser via HTTPS
(https://ec2-www-xxx-yyy-zzz.compute-1.amazonaws.com/ in this example), and
start configuring the rest of Juju with the GUI.  You should see a similar
web address.  Accessing the GUI via HTTP will redirect to using HTTPS.

By default, the deployment uses self-signed certificates. The browser will ask
you to accept a security exception once.

You will see a login form with the username fixed to "user-admin" (for juju-
core) or "admin" (for pyjuju). The password is the same as your Juju
environment's `admin-secret`, found in `~/.juju/environments.yaml`.

### Deploying to a chosen machine ###

The instructions above cause you to use a separate machine to work with the
GUI.  If you'd like to reduce your machine footprint (and perhaps your costs),
you can colocate the GUI with the Juju bootstrap node.

This approach might change in the future (possibly with the Juju shipped with
Ubuntu 13.10), so be warned.

The instructions differ depending on the Juju implementation.

#### juju-core ####

Replace "juju deploy cs:precise/juju-gui" from the previous
instructions with this:

    juju deploy --force-machine 0 cs:precise/juju-gui

#### pyjuju ####

Colocation support is not included by default in the pyjuju implementation; to
activate it, you will need to install Jitsu:

    sudo apt-get install juju-jitsu

and then replace "juju deploy cs:precise/juju-gui" from the previous
instructions with this:

    jitsu deploy-to 0 cs:precise/juju-gui

## Contacting the Developers ##

If you run into problems with the charm, please feel free to contact us on the
[Juju mailing list](https://lists.ubuntu.com/mailman/listinfo/juju), or on
Freenode's IRC network on #juju.  We're not always around (working hours in
Europe and North America are your best bets), but if you send us a mail or
ping "jujugui" we will eventually get back to you.

If you want to help develop the charm, please see the charm's `HACKING.md`.
