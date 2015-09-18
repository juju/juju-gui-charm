#!/bin/bash
ADDRESS='http://127.0.0.1/juju-ui/version.js'
LIFE_SIGN='jujuGuiVersionInfo'

match=$(curl -s $ADDRESS | grep "$LIFE_SIGN")

if [[ -z $match ]]; then
    echo juju-gui did not return content indicating it was loading.
    exit 2
fi

echo "All Good"
