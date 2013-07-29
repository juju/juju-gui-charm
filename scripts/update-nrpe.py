#!/usr/bin/env python
from charmsupport import nrpe


def update_nrpe_config():
    nrpe_compat = nrpe.NRPE()
    nrpe_compat.add_check(
        'front-page', 'Check font page loads', 'check-front-paget.sh')
    nrpe_compat.write()


if __name__ == '__main__':
    update_nrpe_config()
