#!/bin/bash
ADDRESS='https://127.0.0.1/static/gui/build/app/version.json'
LIFE_SIGN='version'

match=$(curl -sk $ADDRESS | grep "$LIFE_SIGN")

if [[ -z $match ]]; then
    echo juju-gui did not return content indicating it was loading.
    exit 2
fi

echo "All Good"
