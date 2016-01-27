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

.PHONY: all
all: setup

# The virtualenv is created by the 00-setup script and not here. This way we
# support the juju-test plugin, which calls the executable files in
# alphabetical order.
.PHONY: setup
setup: releases
	tests/00-setup
	# Ensure the correct version of pip has been installed.
	# 1.4.x - 1.9.x or 6.x or 7.x
	tests/.venv/bin/pip --version | grep -E '1\.[4-9]\.|[6-7]\.[0-9]\.[0-9]' || exit 1

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
	@$(VENV)/bin/flake8 --show-source --exclude=.venv \
		--filename *.py,20-functional.test \
		hooks/ tests/ server/

.PHONY: clean-tests
clean-tests:
	rm -rf tests/download-cache
	rm -rf tests/.venv

.PHONY: clean
clean: clean-tests
	find . -name '*.pyc' -delete
	rm -rf $(VENV)
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
	@echo '  "precise" and "trusty".'
