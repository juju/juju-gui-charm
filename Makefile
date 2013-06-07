# Juju GUI Makefile.

JUJUTEST = juju-test --timeout=30m -v -e "$(JUJU_ENV)" --upload-tools
VENV = ./tests/.venv

all: setup

setup:
	@./tests/00-setup

unittest: setup
	./tests/10-unit.test

ftest: setup
	$(JUJUTEST) 20-functional.test

# This will be eventually removed when we have juju-test --clean-state.
test: unittest ftest

# This will be eventually renamed as test when we have juju-test --clean-state.
jujutest:
	$(JUJUTEST)

lint: setup
	@flake8 --show-source --exclude=.venv  ./hooks/ ./tests/

clean:
	find . -name '*.pyc' -delete
	rm -rf $(VENV)

deploy: setup
	$(VENV)/bin/python ./tests/deploy.py

help:
	@echo -e 'Juju GUI charm - list of make targets:\n'
	@echo -e 'make - Set up development and testing environment.\n'
	@echo 'make test JUJU_ENV="my-juju-env" - Run functional and unit tests.'
	@echo -e '  JUJU_ENV is the Juju environment that will be bootstrapped.\n'
	@echo -e 'make unittest - Run unit tests.\n'
	@echo 'make ftest JUJU_ENV="my-juju-env" - Run functional tests.'
	@echo -e '  JUJU_ENV is the Juju environment that will be bootstrapped.\n'
	@echo -e 'make lint - Run linter and pep8.\n'
	@echo -e 'make clean - Remove bytecode files and virtualenvs.\n'
	@echo 'make deploy [JUJU_ENV="my-juju-env]" - Deploy and expose the Juju'
	@echo '  GUI charm setting up a temporary Juju repository. Wait for the'
	@echo '  service to be started.  If JUJU_ENV is not passed, the charm will'
	@echo '  be deployed in the default Juju environment.'

.PHONY: all clean deploy ftest help jujutest lint setup test unittest
