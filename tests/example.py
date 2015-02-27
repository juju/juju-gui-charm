# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2013 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Example data used in tests."""


def get_bundles(bootstrap_node_series):
    """Return example bundles used in functional tests.

    Since bundle units are co-located in order to speed up the test, the given
    bootstrap node series is used to determine the series used by co-located
    services.
    """
    mysql_charms = {
        'precise': 'cs:precise/mysql-51',
        'trusty': 'cs:trusty/mysql-20',
    }
    haproxy_charms = {
        'precise': 'cs:precise/haproxy-35',
        'trusty': 'cs:trusty/haproxy-4',
    }
    return (
        _bundle1.format(mysql=mysql_charms[bootstrap_node_series]),
        _bundle2.format(mediawiki=haproxy_charms[bootstrap_node_series]),
    )


_bundle1 = """
bundle1:
  series: trusty
  services:
    wordpress:
      charm: "cs:precise/wordpress-15"
      num_units: 2
      options:
        debug: "no"
        engine: nginx
        tuning: single
        "wp-content": ""
      constraints: "cpu-cores=4,mem=4000"
      annotations:
        "gui-x": 313
        "gui-y": 51
    mysql:
      charm: "{mysql}"
      num_units: 1
      to: '0'
      options:
        "block-size": 7
        "dataset-size": "42%"
        flavor: percona
      annotations:
        "gui-x": 669.5
        "gui-y": -33.5
  relations:
    - - "wordpress:db"
      - "mysql:db"
"""

_bundle2 = """
b undle2:
  services:
    mediawiki:
      charm: "{mediawiki}"
      num_units: 1
      to: '0'
      options:
        global_maxconn: 4242
      annotations:
        "gui-x": 432
        "gui-y": 120
  relations: []
"""
