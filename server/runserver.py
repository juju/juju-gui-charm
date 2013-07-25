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

"""Juju GUI server entry point.

Arguments example:
    --guiroot="/var/lib/juju/agents/unit-juju-gui-0/charm/juju-gui/build-prod"
    --apiurl="wss://ec2-75-101-177-185.compute-1.example.com:17070"
    --apiversion="go"
"""

from guiserver import manage


if __name__ == '__main__':
    manage.setup()
    manage.run()
