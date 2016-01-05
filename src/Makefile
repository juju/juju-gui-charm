# This file is part of the Juju GUI, which lets users view and manage Juju
# environments within a graphical interface (https://launchpad.net/juju-gui).
# Copyright (C) 2012-2015 Canonical Ltd.
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

JUJU_GUI_PROJECT = https://github.com/juju/juju-gui.git
JUJU_GUI_BRANCH ?= 

.PHONY: juju-gui
juju-gui:
	rm -rf juju-gui
ifdef JUJU_GUI_BRANCH
	git clone --branch master $(JUJU_GUI_BRANCH)
else
	git clone --depth 1 --branch master $(JUJU_GUI_PROJECT)
endif

.PHONY: package
package: juju-gui
	cd juju-gui && git pull
	$(MAKE) -C juju-gui dist
	$(MAKE) -C juju-gui collect-requirements

