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

VENV = tests/.venv
# Keep SYSDEPS in sync with tests/tests.yaml.
SYSDEPS = build-essential bzr charm-tools firefox libapt-pkg-dev \
	libpython-dev python-apt python-virtualenv rsync xvfb

CHARMCMD := charm
CHARMURL ?= cs:~juju-gui-charmers/juju-gui

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

.PHONY: test
test: setup
	tests/10-unit.test
	tests/11-server.test

.PHONY: lint
lint: setup
	@$(VENV)/bin/flake8 --show-source \
		--exclude=.venv,charmhelpers \
		--filename *.py,config-changed,start,stop,upgrade-charm \
		hooks/ tests/ server/

.PHONY: check
check: clean lint test

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

.PHONY: publish-development
publish-development: push-to-charmstore
	$(CHARMCMD) publish --channel development $(fullurl)

.PHONY: publish-stable
publish-stable: push-to-charmstore
	$(CHARMCMD) publish $(fullurl)

.PHONY: push-to-charmstore
push-to-charmstore: clean
	$(CHARMCMD) login
	@echo $(CHARMCMD) push . $(CHARMURL)
	$(eval fullurl = $(shell $(CHARMCMD) push . $(CHARMURL) | grep 'url: ' | awk -F 'url: ' '{print $$2}'))

.PHONY: sync
sync:
	scripts/charm_helpers_sync.py -d hooks/charmhelpers -c charm-helpers.yaml

.PHONY: help
help:
	@echo -e 'Juju GUI charm - list of make targets:\n'
	@echo -e 'make sysdeps - Install the required system packages.\n'
	@echo -e 'make - Set up development and testing environment.\n'
	@echo -e 'make test - Run unit tests.\n'
	@echo -e 'make lint - Run linter and pep8.\n'
	@echo -e 'make check - Run both unit tests and linter.\n'
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
	@echo 'make publish-development - Push and publish the charm to the'
	@echo -e '  development channel.\n'
	@echo 'make publish-stable - Push and publish the charm to the'
	@echo -e '  stable channel.\n'
	@echo -e 'make sync - Update the version of charmhelpers.\n'
