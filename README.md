# Juju GUI Charm #

This charm makes it easy to deploy a Juju GUI into an existing environment.


## Warning ##

The GUI and charm have two important limitations that we are actively working
on.  We plan to publicly announce this charm once these limitations are
resolved.  We expect this to happen in early January, 2013.

First, there is no security.  Anyone who can connect to your machines can
connect to the websocket that controls your Juju instance.  To mitigate the
problem, make sure that the machine that runs your GUI charm can only be
accessed by machines you control.  The upcoming solution will use HTTPS and a
password (specifically, your Juju environment's admin-secret).

Second, the charm uses the GUI trunk by default, rather than a release.  This
introduces unnecessary fragility and slowness.  Again, we are working to fix
this.


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

Finally, you need to identify the GUI's URL--sadly, the most annoying part of
the process at the moment.  Right now (see the warning section above about not
yet working with GUI releases) it can take an excessive amount of time for the
GUI to be built and to start--20 minutes or more.  This command will let you
see when it is ready to go by giving you regular status updates:

    $ watch juju status

Eventually, after many minutes, at the end of the status you will hopefully see
something that looks like this:

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
            <!--- Uncomment when TLS connections are re-enabled.
            - 443/tcp
            -->
            - 8080/tcp
            public-address: ec2-204-236-250-8.compute-1.amazonaws.com

That tells me I can go to the public-address in my browser via HTTPS
(https://ec2-204-236-250-8.compute-1.amazonaws.com/ in this example), and start
configuring the rest of Juju with the GUI.  You should see something similar.
(Accessing the GUI via HTTP will redirect to using HTTPS anyway.)

Again, until we switch to releases, the charm is fragile.  As I write this,
when run within the charm, the GUI appears to not be connecting properly to
Juju.  Until the charm works with QA'd releases rather than branches (soon!),
be prepared for unpleasant surprises like this.


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
freenode's IRC network on #juju.  We're not always around (working hours in
Europe and NA are your best bets), but if you send us a mail or ping "jujugui"
we will eventually get back to you.

If you want to help develop the charm, please see the charm's HACKING.txt.
