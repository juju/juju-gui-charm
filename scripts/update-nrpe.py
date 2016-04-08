#!/usr/bin/env python
import sys
import charmsupport.nrpe


def get_nrpe():
    nrpe = charmsupport.nrpe.NRPE()
    nrpe.add_check('app-is-accessible',
                   'Check_the_app_can_be_downloaded',
                   'check-app-access.sh')
    return nrpe


def update_nrpe_config():
    nrpe = get_nrpe()
    nrpe.write()


def remove_nrpe_check():
    nrpe = get_nrpe()
    nrpe.remove_checks()


if __name__ == '__main__':
    hook_name = sys.argv[0]
    if 'departed' in hook_name or 'broken' in hook_name:
        remove_nrpe_check()
    else:
        update_nrpe_config()
