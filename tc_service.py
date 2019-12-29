from tornado.ioloop import IOLoop
from tornado.web import Application, RequestHandler
from tornado.websocket import WebSocketHandler
from tornado.httpserver import HTTPServer
from datetime import datetime
from threading import Thread
from shutil import rmtree
from time import sleep
from socket import gethostname, gethostbyname

import os
import sys
import json
import requests
import tempfile

# VERSION
VERSION_MAJOR = 0
VERSION_MINOR = 1
VERSION_PATCH = 0

DEBUG = True if '-d' in sys.argv else False

# DIRS AND FILES
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOME_DIR = os.getenv("HOME")
HOSTNAME = gethostname()
DATA_DIR = f"{BASE_DIR}/data" if DEBUG else f"{HOME_DIR}/tc-data"
LOG_FILE = f"{DATA_DIR}/logs.csv"
DEV_FILE = f"{DATA_DIR}/devices.json"

INTERVAL = 30 # Data interval in minutes
CLNT_WS  = None
USER     = os.getenv("USER")
COMMAND  = "curl http://localhost:8000/data"
COMMENT  = "# tc-server"

BOARDS = {}

TELEGRAM_TOKEN  = os.getenv("TGTOKEN", default='')
TELEGRAM_CHATID = os.getenv("TGCHATID", default='')


#########
# Utils #
#########

def get_version() -> str:
    return '.'.join(map(str, [VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH]))


def time_stamp() -> str:
    """Get timestamp"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


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


def write_data(fp: str, data: str) -> None:
    """Write data in csv format"""
    if os.path.isfile(fp):
        with open(fp, 'a') as f:
            d = data if "\n" in data else f"{data}\n"
            f.write(d)
        f.close()


def log(fp, log_type, msg, telegram=False) -> None:
    timestamp = time_stamp()
    write_data(fp, f"{timestamp},{log_type},{msg}")
    if telegram and not DEBUG:
        msg = f"{log_type.upper()}: {msg} at {timestamp}"
        telegram_msg(msg)
    else:
        print(msg)


def _get_cronjobs() -> list:

    from subprocess import Popen, PIPE
  
    process = Popen(['crontab', '-u', USER, '-l'], stdout=PIPE, stderr=PIPE)
    lines = process.stdout.readlines()
    return lines


def _job_exist(command) -> bool:
    for line in _get_cronjobs():
        if command in line.decode():
            return True
    return False


def job_exists() -> bool:
    for line in _get_cronjobs():
        if COMMENT in line.decode():
            return True
    return False


def set_job(command, time, full=False) -> None:  # only in minutes
    t = time
    if _job_exist(command):
        remove_job(command)

    jobs = _get_cronjobs()
    if full:
        jobs.append(bytes(f"{command} {COMMENT}\n".encode()))
    else:
        jobs.append(bytes(f"*/{t} * * * * {command} {COMMENT}\n".encode()))
    _write_jobs(jobs)


def remove_job(command) -> None:
    jobs = _get_cronjobs()
    for job in jobs:
        if command in job.decode():
            jobs.remove(job)

    _write_jobs(jobs)  


def remove_jobs() -> None:
    jobs = _get_cronjobs()
    for job in jobs.copy():
        if COMMENT in job.decode():
            jobs.remove(job)

    _write_jobs(jobs)


def _write_jobs(jobs_list) -> None:

    from subprocess import run
    
    f, fp = tempfile.mkstemp()
    with os.fdopen(f, 'wb') as tmpf:
        for job in jobs_list:
            tmpf.write(job)
    tmpf.close()

    run(["crontab", "-u", USER, fp])
    os.remove(fp)


def value_alert(value_type, value, min_value=None, max_value=None):
    pass


############
# Telegram #
############


def telegram_msg(msg) -> None:
    t = Thread(target=_send, args=(msg,))
    t.start()


def _send(msg) -> None:
    url = "https://api.telegram.org"
    query = f"/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={TELEGRAM_CHATID}&" \
            f"parse_mode=Markdown&text={msg}"
    res = None
    try:
        res = requests.get(url + query).json()
        if not res['ok']:
            pass
    except Exception:
        pass


#########
# Board #
#########


class Board:

    def __init__(self, bid, ip, folder, timec):
        self.id = bid
        self.ip = ip
        self.connection_date = timec
        self.folder = folder
        self.sensors = {}
        self.url = f"http://{ip}:80/data"
        self.on_change_events = False
    
    def set_sensor(self, dsensor) -> None:
        self.sensors.update(dsensor)

    def set_ws(self, ws) -> None:
        self.ws_connection = ws

    def check_conn(self) -> None:
        if self.ws_connection:
            self.ws_connection.ping()

    def as_dict(self) -> dict:
        d = self.__dict__
        return d

    def sensors_list(self) -> list:
        return [s for s in self.sensors.values()]

    def get_data(self, sensor=None) -> int:
        res = None
        if sensor and sensor in self.sensors.keys():
            res = requests.get(self.url, params={"sensor": sensor}).text.split(':')
        return int(res[1])
        

####################
# Tornado Handlers #
####################

# Client Handlers

class MainHandler(RequestHandler):

    def get(self):
        
        devices = []
        for k, dev in BOARDS.items():
            devices.append(dev.as_dict())
        
        response = {
            "cronjobs": job_exists(),
            "host": HOSTNAME,
            "version": get_version(),
            "debug": DEBUG,
            "logs": {
                "len": 0,
                "last_log": {}
            },
            "devices": devices
        }
        self.write(json.dumps(response))


# cambiar, demasiado feo
class DataHandler(RequestHandler):
    
    def get(self):
        action = self.get_argument('action')
        if action == "start":
            opt = self.get_argument('opt')
            for b in BOARDS.values():
                if opt == 'interval':
                    for s in b.sensors_list():
                        set_job(f"{COMMAND}?board={b.id}&sensor={s['id']}", INTERVAL)
                elif opt == 'onchange':
                    requests.get(b.url+'/config?option=sendon')
                    b.on_change_events = True
        
        elif action == "stop":
            opt = self.get_argument('opt')
            if opt == 'interval':
                remove_jobs()
            elif opt == 'onchange':
                for b in BOARDS.values():
                    requests.get(b.url+'/config?option=sendoff')
                    b.on_change_events = False

        # elif action == "clean":
        #     opt = self.get_argument('opt')
        #         rmtree(opt)
        elif action == "info":
            pass


class SafeStop(RequestHandler):
    
    def get(self):
        # check boards
        # save config  
        # save boards 
        # stop websocket
        opt = self.get_argument('opt', None)
        if opt == 'clean':
            rmtree(DATA_DIR)
            if job_exists():
                remove_jobs()

        log(LOG_FILE, "alert", "Server stopped", telegram=True)
        sleep(0.5)
        IOLoop.current().stop()


class GetData(RequestHandler):

    def get(self):

        board_name = self.get_argument("board")
        sensor_name = self.get_argument("sensor")

        board = BOARDS[board_name]
        value = board.get_data(sensor_name)
        timestamp = time_stamp()

        write_data(board.sensors[sensor_name]['interval_file'], f"{timestamp},{value}")


class TelegramConfig(RequestHandler):

    def get(self):
        pass

    def post(self):
        global TELEGRAM_TOKEN
        global TELEGRAM_CHATID

        body = json.loads(self.request.body.decode('utf-8'))

        TELEGRAM_TOKEN = body['token']
        TELEGRAM_CHATID = body['chatid']

        self.write("")


# pendiente
class WebsocketClientHandler(WebSocketHandler):
    
    def check_origin(self, origin):
        return True

    def open(self):
        global CLNT_WS
        self.client_ip = self.request.remote_ip
        log(LOG_FILE, 'alert', f'Client IP {self.client_ip} connected', telegram=True)
        board = None
        for k, v in BOARDS.items():
            board = v
        openRes = {
            "type": "open",
            "host": HOSTNAME,
            "device": board.id if board else "No Device",
            "status": "On" if board.on_change_events else "Off",
            "version": get_version(),
            "sensors": board.sensors_list() if board else []
        }
        for s in openRes['sensors']:
            s.update({"value": board.get_data(s['id'])})
        self.write_message(openRes)
        CLNT_WS = self

    def on_close(self):
        global CLNT_WS
        CLNT_WS = None
        log(LOG_FILE, 'alert', f'Client IP {self.client_ip} disconnected', telegram=True)


# Board Handlers

class WebsocketDataListener(WebSocketHandler):

    def check_origin(self, origin):
        return True

    def open(self):
        self.id = self.get_argument('id', default=None)
        self.device_ip = self.request.remote_ip
        if self.id not in BOARDS.keys():
            sens = self.get_argument('sens').split(':')
            timestamp = time_stamp()
            folder = f"{DATA_DIR}/{self.id}_{timestamp.split(' ')[0]}"
            board = Board(self.id, self.device_ip, folder, timestamp)
            for s in sens:
                t = self.get_argument(s).split(':')
                board.set_sensor({s: {
                    "id": s,
                    "type": t[0],
                    "measure": t[1],
                    "alert": False,
                    "maxvalue": None,
                    "minvalue": None,
                    "onchange_file": f"{folder}/{s}_{t[0]}_onchange.csv",
                    "interval_file": f"{folder}/{s}_{t[0]}_interval.csv"}
                })
            if not os.path.isdir(folder):
                os.makedirs(folder)
                for k, v in board.sensors.items():
                    with open(v['onchange_file'], 'w+') as f:
                        f.write("TimeStamp, Value\n")
                        f.close()
                    with open(v['interval_file'], 'w+') as f:
                        f.write("TimeStamp, Value\n")
                        f.close()

            BOARDS.update({board.id: board})
            if os.path.isfile(DEV_FILE) and not DEBUG:
                dev = read_json(DEV_FILE)
                dev['devices'].append(board)
                write_json(DEV_FILE, dev)
            elif not DEBUG:
                write_json(DEV_FILE, {"devices": [board.as_dict()]})
            print(board.as_dict())

        log(LOG_FILE, "alert", f"Device {self.id} IP {self.device_ip} is Connected", telegram=True)

    def on_message(self, message):
        global CLNT_WS
        print(message)
        data = message.split(':')
        sen = data[0]
        ivalue = int(data[1])
        timestamp = time_stamp()
        board = BOARDS[self.id]
        sensor = board.sensors[sen]
        if CLNT_WS:
            CLNT_WS.write_message({
                "type": "value",
                "board": board.id,
                "sensor": sen,
                "value": ivalue
            })

        if sensor['alert']:
            value_alert(sensor['type'], sensor['minvalue'], sensor['maxvalue'])

        write_data(sensor['onchange_file'], f"{timestamp},{ivalue}")

    def on_close(self):
        log(LOG_FILE, "alert", f"Device {self.id} is Disconnected", telegram=True)
        print("Client Disconnected")

    def check_status(self):
        pass
            

URLS = [
    (r"/", MainHandler),
    (r"/data", GetData),
    (r"/config/data", DataHandler),
    (r"/config/telegram", TelegramConfig),
    (r"/server/stop", SafeStop),
    (r"/ws/board", WebsocketDataListener),
    (r"/ws/client", WebsocketClientHandler)]


def main():

    log(LOG_FILE, "alert", "Server started", telegram=True)

    # Creación de directorios y archivos
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR)

    if not os.path.isfile(LOG_FILE):
        with open(LOG_FILE, 'w+') as f:
            f.write("TimeStamp, Type, Message\n")
        f.close()

    # chequea si existe archivo con dispositivos
    if os.path.isfile(DEV_FILE):
        devices = read_json(DEV_FILE)   
        for d in devices['devices']:
            board = Board(d['id'], d['ip'], d['folder'], d['connection_date'])
            board.set_sensor(d['sensors'])
            BOARDS.update({board.id: board})

    # "auto update" every day at 00:01
    if not DEBUG:
        set_job("1 0 * * * {BASE_DIR}/tc_cli.py update")

    # Inicio del servidor
    app = Application(URLS)
    server = HTTPServer(app)
    server.listen(8000)
    IOLoop.current().start()


if __name__ == '__main__':
    main()
