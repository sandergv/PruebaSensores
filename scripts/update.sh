#!/bin/bash
SCRIPTPATH=$(dirname $(dirname $(realpath -s $0)))
git pull
sleep 3
cd $SCRIPTPATH
nohup python3 "$SCRIPTPATH/tc_service.py" &
