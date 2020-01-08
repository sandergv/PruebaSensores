#!/usr/bin/env python3
# TO-DO
# Clean data
# Config server
# Get data 
# Show data with filters
# Show logs
# Gen csv with Simple data
from datetime import datetime

import sys
import os
import requests
import csv
import json
import argparse


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = f"{BASE_DIR}/config.json"
DATA_DIR = ""
HOST = 'localhost'
PORT = 8000

def read_json(fp: str) -> dict:
    """Read data from json file"""
    d = {}
    if os.path.isfile(fp):
        with open(fp, 'r') as f:
            d = json.load(f)
        f.close()
    return d


def write_json(fp: str, data: dict) -> None:
    """Write data to json file"""
    with open(fp, 'w+') as f:
        json.dump(data, f, indent=2)
    f.close()


def simple_data_csv(fp, ):
    pass


if __name__ == "__main__":


    if os.path.isfile(CONFIG_FILE):
        config = read_json(CONFIG_FILE)
        host = config['service']['host']
        ip = '127.0.0.1' if host == 'localhost' else host
        port = config['service']['port']
        url = f"http://{host}:{port}"

    aparser = argparse.ArgumentParser("TC-Cli")
    
    sub = aparser.add_subparsers(dest="command")
    
    # Init
    args_init = sub.add_parser('init', help="")
    args_init.add_argument('-r', '--remote', metavar='IP', help="Add remote IP")

    # Service
    args_service = sub.add_parser('service', help="")
    args_service.add_argument('-s', '--shutdown', action='store_true')

    # Session
    args_session = sub.add_parser('session', help="Create, delete and list sessions")
    session_sub = args_session.add_subparsers(dest='session_command')
    
    # New Session
    args_new_session = session_sub.add_parser('new', help="New session")
    args_new_session.add_argument('board')
    args_new_session.add_argument('sensor')
    args_new_session.add_argument('-d', '--description', choices=['onchange', 'interval'], default='onchange')
    args_new_session.add_argument('-t', '--type', choices=['open', 'scheduled'], default='open')
    args_new_session.add_argument('-i', '--interval', nargs='*', default=[], metavar=('type', 'interval'))
    args_new_session.add_argument('-s', '--start', default=False)
    args_new_session.add_argument('-f', '--finish', default=False)
    args_new_session.add_argument('-a', '--alert', nargs='*', metavar=('min', 'max'))

    args_finish_session = session_sub.add_parser('finish', help="Finish session")
    
    # Info Session
    args_info_session = session_sub.add_parser('info', help="Session info")
    args_info_session.add_argument('board')
    args_info_session.add_argument('sensor')

    # list Sessions
    args_list_session = session_sub.add_parser('list', help="Session list")
    args_list_session.add_argument('board')
    args_list_session.add_argument('-d', '--details', action='store_true')

    # Device
    args_device = sub.add_parser('device', help="Device info and data")
    args_device.add_argument('board')

    # info
    args_info = sub.add_parser('info', help="Service info")

    # Update
    args_update = sub.add_parser('update', help="")
    
    args = aparser.parse_args()

    if args.command == 'init':
        initial_config = {
            "basedir": BASE_DIR,
            "service": {
                "remote": False if not args.remote else True,
                "host": HOST if not args.remote else args.remote,
                "port": PORT 
            }
        }
        write_json(CONFIG_FILE, initial_config)
        
    elif args.command == 'config':
        pass

    elif args.command == 'service':    
        if args.shutdown:
            requests.get(url+"/server/stop", params={"opt": "clean"})
    
    elif args.command == 'update':
        from subprocess import run

        requests.get(url+"/server/stop")
        run(['bash', f"{BASE_DIR}/scripts/update.sh"])

    elif args.command == 'session':
        # validar fechas y listas
        if args.session_command == 'new':
            session = {
                "board": args.board,
                "sensor": args.sensor,
                "session": {
                    "type": args.type,
                    "description": args.description,
                    "interval_type": args.interval[0] if args.interval else False,
                    "interval":  int(args.interval[1]) if args.interval else False,
                    "start_date": args.start,
                    "finish_date": args.finish,
                    "alert": True if args.alert else False,
                    "min_value": int(args.alert[0]) if args.alert else False,
                    "max_value": int(args.alert[1]) if args.alert else False
                }
            }
            print(session)
            res = requests.post(url+"/session/"+args.board, data=json.dumps(session))
            print(res)

        elif args.session_command == 'finish':
            requests.get(url+'/session/finish',
                params={"board": "ESP1","sensor": "dht11", "session": "200107221006"})



        elif args.session_command == 'list':
            res = requests.get(url+"/session/list", params={"board": args.board}).json()
            print(res)

    elif args.command == 'info':
        res = requests.get(url).json()
        print(res)            