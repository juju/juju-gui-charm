#!/usr/bin/env python
import sys

from charmhelpers.contrib.charmsupport import nrpe


def update_nrpe_checks():
    nrpe_compat = nrpe.NRPE()
    # The use of port 80 assumes the 'secure' charm configuration
    # value is false, which is the scenario for our deployment on
    # staging and production. If testing this functionality on a
    # free-standing GUI charm deployment be sure to change the secure
    # setting.
    port = 80
    ip_address = '127.0.0.1'
    uri = '/static/gui/build/app/version.json'
    success = 'version'
    check_cmd = 'check_http -I {} -p {} -r {} -u {}'.format(
        ip_address, port, success, uri)
    nrpe_compat.add_check(
        shortname='gui_is_accessible',
        description='Check_the_GUI_responds',
        check_cmd=check_cmd)
    nrpe_compat.write()


def remove_nrpe_check():
    nrpe_compat = nrpe.NRPE()
    nrpe_compat.remove_checks()


if __name__ == '__main__':
    hook_name = sys.argv[0]
    if 'departed' in hook_name or 'broken' in hook_name:
        remove_nrpe_check()
    else:
        update_nrpe_checks()
