#!/bin/bash
SCRIPTPATH=$(dirname $(dirname $(realpath -s $0)))
#git pull
nohup python3 "$SCRIPTPATH/tc_service.py"