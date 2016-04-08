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

JUJUTEST = yes | juju-test --timeout=60m -v --upload-tools -e "$(JUJU_ENV)"
VENV = tests/.venv
# Keep SYSDEPS in sync with tests/tests.yaml.
SYSDEPS = build-essential bzr charm-tools firefox libapt-pkg-dev \
	libpython-dev python-virtualenv rsync xvfb

CHARMCMD := charm2
YELLOW_CS_URL ?= cs:~yellow/trusty/juju-gui
PROMULGATED_CS_URL ?= cs:~juju-gui-charmers/trusty/juju-gui

.PHONY: all
all: setup

# The virtualenv is created by the 00-setup script and not here. This way we
# support the juju-test plugin, which calls the executable files in
# alphabetical order.
.PHONY: setup
setup:
	tests/00-setup

.PHONY: sysdeps
sysdeps:
	sudo apt-get install --yes $(SYSDEPS)

.PHONY: unittest
unittest: setup
	tests/10-unit.test
	tests/11-server.test

.PHONY: ensure-juju-env
ensure-juju-env:
ifndef JUJU_ENV
	$(error JUJU_ENV must be set.  See HACKING.md)
endif

.PHONY: ensure-juju-test
ensure-juju-test: ensure-juju-env
	@which juju-test > /dev/null \
		|| (echo 'The "juju-test" command is missing.  See HACKING.md' \
		; false)

.PHONY: ftest
ftest: setup ensure-juju-test
	$(JUJUTEST) 20-functional.test

# This will be eventually removed when we have juju-test --clean-state.
.PHONY: test
test: unittest ftest

# This will be eventually renamed as test when we have juju-test --clean-state.
.PHONY: jujutest
jujutest:
	$(JUJUTEST)

.PHONY: lint
lint: setup
	@$(VENV)/bin/flake8 --show-source \
		--exclude=.venv,charmhelpers \
		--filename *.py,20-functional.test \
		hooks/* tests/ server/

.PHONY: clean-tests
clean-tests:
	rm -rf tests/download-cache
	rm -rf $(VENV)

.PHONY: clean
clean: clean-tests
	find . -name '*.pyc' -delete
	$(MAKE) -C src clean

.PHONY: deploy
deploy: setup
	$(VENV)/bin/python tests/deploy.py

.PHONY: releases
releases:
	$(MAKE) -C src package
	cp -r src/juju-gui/dist/* releases
	cp -r src/juju-gui/collected-requirements/* jujugui-deps
	$(MAKE) -C src clean

.PHONY: package
package: clean releases

.PHONY: sync
sync: 
	scripts/charm_helpers_sync.py -d hooks/charmhelpers -c charm-helpers.yaml

.PHONY: publish-yellow
publish-yellow: clean
	$(CHARMCMD) upload --publish . $(YELLOW_CS_URL)

.PHONY: publish-promulgated
publish-promulgated: clean
	$(CHARMCMD) upload --publish . $(PROMULGATED_CS_URL)

.PHONY: help
help:
	@echo -e 'Juju GUI charm - list of make targets:\n'
	@echo -e 'make sysdeps - Install the required system packages.\n'
	@echo -e 'make - Set up development and testing environment.\n'
	@echo 'make test JUJU_ENV="my-juju-env" - Run functional and unit tests.'
	@echo -e '  JUJU_ENV is the Juju environment that will be bootstrapped.\n'
	@echo -e 'make unittest - Run unit tests.\n'
	@echo 'make ftest JUJU_ENV="my-juju-env" - Run functional tests.'
	@echo -e '  JUJU_ENV is the Juju environment that will be bootstrapped.\n'
	@echo -e 'make lint - Run linter and pep8.\n'
	@echo -e 'make clean - Remove bytecode files and virtualenvs.\n'
	@echo -e 'make clean-tests - Clean up tests directory.\n'
	@echo 'make package - Download Juju GUI source, build a package,'
	@echo -e '  and collect dependencies. Ready to deploy or upload.\n'
	@echo 'make deploy [JUJU_ENV="my-juju-env"] [SERIES="trusty"] - Deploy and'
	@echo '  expose the Juju GUI charm setting up a temporary Juju repository.'
	@echo '  Wait for the service to be started. If JUJU_ENV is not passed,'
	@echo '  the charm will be deployed in the default Juju environment.'
	@echo '  If SERIES is not passed, "trusty" is used. Possible values are'
	@echo -e '  "precise" and "trusty".\n'
	@echo -e 'make sync - Update the version of charmhelpers.\n'
	@echo -e 'make publish-yellow - Upload and publish the charm to the ~yellow namespace.\n'
	@echo -e 'make publish-promulgated - Upload and publish the charm to cs:juju-gui.\n'
