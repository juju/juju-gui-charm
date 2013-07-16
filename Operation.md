<!--
Operation.md
Copyright 2013 Canonical Ltd.
This work is licensed under the Creative Commons Attribution-Share Alike 3.0
Unported License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/3.0/ or send a letter to Creative
Commons, 171 Second Street, Suite 300, San Francisco, California, 94105, USA.
-->

# Juju GUI Charm Operation #

## How it works ##

The Juju GUI is a client-side, JavaScript application that runs inside a web
browser. The browser connects to a single server deployed by the charm.

## Server ##


The server directly serves static files to the browser, including
images, HTML, CSS and JavaScript files via an HTTPS connection.

It also acts as a proxy between the browser and the Juju installation that
performs the actual deployment work. Both browser-server and server-Juju
connections are bidirectional via the WebSocket protocol, allowing changes
in the Juju installation to be propagated and shown immediately by the browser.



The GUI server is a custom-made application based on the
[Tornado](http://www.tornadoweb.org/) framework.

It directly serves static files to the browser, including images, HTML,
CSS and JavaScript files via an HTTPS connection.

It also acts as a proxy between the browser and the Juju installation that
performs the actual deployment work. Both browser-server and server-Juju
connections are bidirectional via the WebSocket protocol, allowing changes
in the Juju installation to be propagated and shown immediately by the browser.
