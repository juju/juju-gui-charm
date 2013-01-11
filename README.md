# Juju GUI Charm #

This charm makes it easy to deploy a Juju GUI into an existing environment.

## Deploying the Juju GUI ##

Deploying the Juju GUI is accomplished using Juju itself.

You need a configured and bootstrapped Juju environment: see the Juju docs
about [getting started](https://juju.ubuntu.com/docs/getting-started.html),
and then run the usual bootstrap command.

    $ juju bootstrap

Next, you simply need to deploy the charm and expose it.  (See also "Deploying
with Jitsu" below, for another option.)

    $ juju deploy cs:~juju-gui/precise/juju-gui
    $ juju expose juju-gui

Finally, you need to identify the GUI's URL. It can take a few minutes for the
GUI to be built and to start; this command will let you see when it is ready
to go by giving you regular status updates:

    $ watch juju status

Eventually, at the end of the status you will see something that looks like
this:

    services:
      juju-gui:
        charm: cs:~juju-gui/precise/juju-gui-7
        exposed: true
        relations: {}
        units:
          juju-gui/0:
            agent-state: started
            machine: 1
            open-ports:
            - 80/tcp
            - 443/tcp
            - 8080/tcp
            public-address: ec2-204-236-250-8.compute-1.amazonaws.com

That tells me I can go to the public-address in my browser via HTTPS
(https://ec2-204-236-250-8.compute-1.amazonaws.com/ in this example), and start
configuring the rest of Juju with the GUI.  You should see something similar.
(Accessing the GUI via HTTP will redirect to using HTTPS anyway.)

You wil see a login form with the username fixed to "admin". The password is
the same as your Juju environment's `admin-secret`, found in
`~/.juju/environments.yaml`.

### Deploying with Jitsu ###

The instructions above cause you to use a separate machine to work with the
GUI.  If you'd like to reduce your machine footprint (and perhaps your costs),
you can colocate the GUI with the Juju bootstrap node.  This approach will
change in the future (probably with the Juju shipped with Ubuntu 13.04), so be
warned.

For now, though, install Jitsu...

    $ sudo apt-get install juju-jitsu

...and then replace "juju deploy cs:~juju-gui/precise/juju-gui" from the
previous instructions with this:

    $ jitsu deploy-to 0 cs:~juju-gui/precise/juju-gui

## Contacting the Developers ##

If you run into problems with the charm, please feel free to contact us on the
[Juju mailing list](https://lists.ubuntu.com/mailman/listinfo/juju), or on
Freenode's IRC network on #juju.  We're not always around (working hours in
Europe and North America are your best bets), but if you send us a mail or
ping "jujugui" we will eventually get back to you.

If you want to help develop the charm, please see the charm's `HACKING.md`.
