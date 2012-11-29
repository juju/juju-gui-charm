"""Juju GUI charm utilities."""

import os

from shelltoolbox import search_file


def get_zookeeper_address(agent_file):
    """Retrieve the Zookeeper address contained in the given *agent_file*.

    The *agent_file* is a path to a file containing a line similar to the
    following::

        env JUJU_ZOOKEEPER="address"
    """
    line = search_file('JUJU_ZOOKEEPER', agent_file).strip()
    return line.split('=')[1].strip('"')


def render_to_file(template, context, destination):
    """Render the given *template* into *destination* using *context*.

    The arguments *template* is the name or path of the template file: it may
    be either a path relative to ``../config`` or an absolute path.
    The argument *destination* is a file path.
    The argument *context* is a dict-like object.
    """
    template_path = os.path.join(
        os.path.dirname(__file__), '..', 'config', template)
    contents = open(template_path).read()
    with open(destination, 'w') as stream:
        stream.write(contents % context)
