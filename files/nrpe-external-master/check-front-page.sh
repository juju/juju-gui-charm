#!/bin/sh
SITE_CONF='/etc/apache2/sites-available/juju-gui'
ADDRESS='https://127.0.0.1:443/'
LIFE_SIGN='loading on a slow connection'

#SITE_CONF='/etc/hosts'
#ADDRESS='https://jujucharms.com:443/'

if [[ ! -f $SITE_CONF ]]; then
    echo Apache is not configured serve juju-gui.
    exit 2
fi

match=$(curl $ADDRESS | grep "$LIFE_SIGN")

if [[ -n "$match" ]]; then
    exit 0
else
    echo juju-gui did not return content indicating it was loading.
    exit 2
fi
