#!/usr/bin/env python
from charmsupport import nrpe


def update_nrpe_config():
    nrpe_compat = nrpe.NRPE()
    nrpe_compat.add_check(
        'app-is-accessible', 'Check_the_app_can_be_downloaded',
        'check-app-access.sh')
    nrpe_compat.write()


if __name__ == '__main__':
    update_nrpe_config()
