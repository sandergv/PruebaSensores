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

    aparser = argparse.ArgumentParser("TC-Cli")
    
    aparser.add_argument('action', 
        choices=[
            'init',     # Inicializa archivos y parametros necesarios
            'config',   # Modificación de parametros
            'info',     # Info del servicio
            'update',   # Actualización del servicio y cli (Basicamente git pull)
            'device',
            'service'
            ])
    aparser.add_argument('-p', choices=['on', 'off'])
    aparser.add_argument('-o', choices=['on', 'off'])
    aparser.add_argument('-i', choices=['on', 'off'])
    aparser.add_argument('-s', action='store_true')
    aparser.add_argument('-d', action='store_true')
    aparser.add_argument('-r', '--remote', metavar='IP', 
        help='Connect to remote server with the given ip. (init)')


    args = aparser.parse_args()

    act = args.action
    
    if os.path.isfile(CONFIG_FILE):
        config = read_json(CONFIG_FILE)
        host = config['service']['host']
        ip = '127.0.0.1' if host == 'localhost' else host
        port = config['service']['port']
        url = f"http://{host}:{port}"

    if act == 'init':
        initial_config = {
            "basedir": BASE_DIR,
            "service": {
                "remote": False if not args.remote else True,
                "host": HOST if not args.remote else args.remote,
                "port": PORT 
            }
        }
        write_json(CONFIG_FILE, initial_config)
        
    elif act == 'config':
        pass

    elif act == 'service':
        
        if args.p == 'off':
            requests.get(url+"/server/stop", params={"opt": "clean"})

    elif act == 'info':

        info = requests.get(url).json()
        if args.s:
            print(
            f"Host:\t\t{info['host']}\n"
            f"IP:\t\t{ip}\n"
            f"Port:\t\t{config['service']['port']}\n"
            f"Cron Jobs:\t{info['cronjobs']}\n"
            f"Version:\t{info['version']}\n", end=''
        )
        if args.d:
            for d in info['devices']:
                print(
                    "DEVICES:\n"
                    f"ID:\t\t{d['id']}\n"
                    f"IP:\t\t{d['ip']}\n"
                    f"Connection:\t{d['connection_date']}\n"
                    f"URL:\t\t{d['url']}\n"
                    f"OC events:\t{d['on_change_events']}\n"
                    "Sensors:"
                )
                for k, s in d['sensors'].items():
                    print(
                        f"Model:\t\t{k}\n"
                        f"Type:\t\t{s['type']}\n",
                        f"Measure:\t{s['measure']}\n",
                        f"Alert:\t\t{s['alert']}\n",
                    )

    elif act == 'device':
        serv = read_json(CONFIG_FILE)['service']
        url = f"http://{serv['host']}:{PORT}/config/data"
        if args.o == 'on':
            requests.get(
                url,
                params={"action":"start", "opt":"onchange"}
            )
        elif args.o == 'off':
            requests.get(
                url,
                params={"action":"stop", "opt":"onchange"}
            )
        if args.i == 'on':
            requests.get(
                url,
                params={"action":"start", "opt":"interval"}
            )
        elif args.i == 'off':
            requests.get(
                url,
                params={"action":"stop", "opt":"interval"}
            )
    
    elif act == 'update':
        from subprocess import run

        requests.get(url+"/server/stop")
        run(['bash', f"{BASE_DIR}/scripts/update.sh"])