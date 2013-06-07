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
	@echo 'make - Set up development and testing environment.'
	@echo 'make test JUJU_ENV="my-juju-env" - Run functional and unit tests.'
	@echo '  JUJU_ENV is the Juju environment that will be bootstrapped.'
	@echo 'make unittest - Run unit tests.'
	@echo 'make ftest JUJU_ENV="my-juju-env" - Run functional tests.'
	@echo '  JUJU_ENV is the Juju environment that will be bootstrapped.'
	@echo 'make lint - Run linter and pep8.'
	@echo 'make clean - Remove bytecode files and virtualenvs.'
	@echo 'make deploy JUJU_ENV="my-juju-env" - Deploy the Juju GUI charm'
	@echo '  setting up a temporary Juju repository.'
	@echo '  JUJU_ENV is the Juju environment to use to deploy the charm.'

.PHONY: all clean deploy ftest help lint setup test unittest
