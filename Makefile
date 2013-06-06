# Juju GUI Makefile.

all: venv

venv:
	@./tests/00-setup --no-repository

test:
	@juju-test --timeout=30m -v -e "$(ENV)" --upload-tools

unittest: venv
	@./tests/10-unit.test

lint: venv
	@flake8 --show-source --exclude=.venv  ./hooks/ ./tests/

clean:
	find . -name '*.pyc' -delete
	rm -rf ./test/.venv

help:
	@echo -e 'Juju GUI charm - list of make targets:\n'
	@echo 'make - Set up development and testing environment'
	@echo 'make test ENV="my-juju-env" - Run functional and unit tests'
	@echo '  - ENV is the Juju environment to use to deploy the charm'
	@echo 'make unittest - Run unit tests'
	@echo 'make lint - Run linter and pep8'
	@echo 'make clean - Remove bytecode files and virtualenvs'

.PHONY: all clean help lint test unittest venv
