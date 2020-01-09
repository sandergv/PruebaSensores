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
SESS_DIR = f"{DATA_DIR}/sessions"
SESS_FIL = f"{SESS_DIR}/sessions.json"
LOG_FILE = f"{DATA_DIR}/logs.csv"
DEV_FILE = f"{DATA_DIR}/devices.json"

CLNT_WS  = None
USER     = os.getenv("USER")

# Crontab
COMMAND  = 'curl "http://localhost:8000/data'
COMMENT  = "# tc-server"

BOARDS = {}

TELEGRAM_TOKEN  = os.getenv("TGTOKEN", '')
TELEGRAM_CHATID = os.getenv("TGCHATID", '')


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


############
# Telegram #
############


def telegram_msg(msg) -> None:
    
    def send(msg) -> None:
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
    
    t = Thread(target=send, args=(msg,))
    t.start()


###########
# CronTab #
###########

class CronTab:

    class Job:

        def __init__(self, command, comment, day=None, month=None, dow=None):
            self.command = command
            self.comment = comment
            self.minute = 0
            self.hour = 0
            self.day = day
            self.month = month
            self.day_of_week = dow
            self._cron = None
            self._every = False
            
        def every(self, i_type, interval): # type minutes, hours or days
            self._every = True
            interval = f"*/{interval}"
            if i_type == 'minute':
                self._cron = f"{interval} * * * *"
            elif i_type == 'hour':
                self._cron = f"0 {interval} * * *"
            elif i_type == 'day':
                self._cron = f"0 0 {interval} * *" # posible bug

        def get_cron(self):
            if not self._every:
                if self.day and self.month:
                    self._cron = f"0 0 {self.day} {self.month} *"
                elif self.day_of_week:
                    self._cron = f"{self.minute} {self.hour} * * {self.day_of_week}"
            
            return f"{self._cron} {self.command} {self.comment}\n"

        def __repr__(self):
            return self.get_cron()
        
        def __str__(self):
            return self.get_cron()

    jobs = []

    @staticmethod
    def _get_cronjobs() -> list:

        from subprocess import Popen, PIPE
    
        process = Popen(['crontab', '-u', USER, '-l'], stdout=PIPE, stderr=PIPE)
        lines = process.stdout.readlines()
        return [ j.decode() for j in lines]

    @classmethod
    def job_exist(cls, command) -> bool:
        for line in cls._get_cronjobs():
            if command in line:
                return True
        return False

    @classmethod
    def jobs_exist(cls) -> bool:
        for line in cls._get_cronjobs():
            if COMMENT in line:
                return True
        return False

    @classmethod
    def new_job(cls, command):
        
        job = cls.Job(command, COMMENT)
        if str(job) not in [ str(j) for j in cls.jobs ]:
            cls.jobs.append(job)
            return job
        return None

    @classmethod
    def remove_job(cls, job) -> None:
        jobs = cls._get_cronjobs()
        for cjob, ljob in zip(jobs, cls.jobs):
            if job in cjob:
                jobs.remove(cjob)
            if cjob in str(ljob):
                cls.jobs.remove(ljob)
        
        cls._write(jobs)
        
    @classmethod
    def clear_jobs(cls) -> None:
        jobs = cls._get_cronjobs()
        for job in jobs.copy():
            if COMMENT in job:
                jobs.remove(job)
            cls.jobs = []
        cls._write(jobs)

    @classmethod
    def _write(cls, jlist):

        from subprocess import run
        
        f, fp = tempfile.mkstemp()
        with os.fdopen(f, 'wb') as tmpf:
            for job in jlist:
                tmpf.write(bytes(f"{job}".encode()))
        tmpf.close()

        run(["crontab", "-u", USER, fp])
        os.remove(fp)

    @classmethod
    def write(cls) -> None:
        all_jobs = cls._get_cronjobs()    
        jlist = []

        for job in cls.jobs:
            if str(job) not in all_jobs:
                jlist.append(job)

        cls._write(all_jobs+jlist)


#########
# Board #
#########

class Board:

    class Session:

        _session_url = f'http://localhost:8000/session'
        
        def __init__(self, board, sensor, description, stype=None, interval_type=None, interval=None,
            start_date=None, finish_date=None,
            alert=False, min_value=None, max_value=None):

            date = datetime.now().strftime('%y%m%d%H%M%S')
            self.id = f"{date}"
            self.board = board
            self.sensor = sensor
            self.type = stype # open or scheduled
            self.description = description # onchange, interval
            self.interval_type = interval_type
            self.interval = interval
            self.start_date = start_date
            self.finish_date = finish_date
            self.alert = alert
            self.finished = False
            self.min_value = min_value
            self.max_value = max_value
            self._start_job = None
            self._finish_job = None
            self._data_job = None
            self.active = False
            self.folder = f"{SESS_DIR}/{board}_{sensor}"
            self.file = f"{self.folder}/{description}_{date}.csv"

            if not os.path.isdir(self.folder):
                os.makedirs(self.folder)
            
            if not os.path.isfile(self.file):
                with open(self.file, 'w+') as f:
                    f.write('TimeStamp,Value\n')

            if start_date:
                command = f'curl "{self._session_url}/start?board={board}&sensor={sensor}&session={date}"'
                job = CronTab.new_job(command)
                job.month = int(start_date.split('-')[1])
                job.day = int(start_date.split('-')[2])
                self._start_job = job

            if finish_date:
                command = f'curl "{self._session_url}/finish?board={board}&sensor={sensor}&session={date}"'
                job = CronTab.new_job(command)
                job.month = int(finish_date.split('-')[1])
                job.day = int(finish_date.split('-')[2])
                self._finish_job = job
                
            if start_date or finish_date:
                CronTab.write()

            self.save_session()

        def start(self, url=None):
            self.active = True
            if self.description == 'interval':
                command = f'curl "{url}?board={self.board}&sensor={self.sensor}&session={self.id}"'
                job = CronTab.new_job(command)
                job.every(self.interval_type, self.interval)
                self._data_job = job
                CronTab.write()
                self.save_session()

        def finish(self, clean=False):
            self.active = False
            self.finished = True
            if self.description == 'interval':
                CronTab.remove_job(self._data_job.command)
                sessions = read_json(SESS_FIL)
                if clean:
                    sessions['sessions'].pop(self.id)
                    write_json(SESS_FIL, sessions)
                else:
                    self.save_session()

        def save_session(self):
            session = {
                "id": self.id,
                "board": self.board,
                "sensor": self.sensor,
                "description": self.description,
                "type": self.type,
                "interval_type": self.interval_type,
                "interval": self.interval,
                "start_date": self.start_date,
                "finish_date": self.finish_date,
                "file": self.file,
                "active": self.active,
                "finished": self.finished,
                "alert": {
                    "status": self.alert,
                    "min_value": self.min_value,
                    "max_value": self.max_value
                }
            }
            sessions = read_json(SESS_FIL)
            if self.id in sessions['sessions'].keys():
                sessions['sessions'][self.id] = session
            else:
                sessions['sessions'].update({self.id: session})
            write_json(SESS_FIL, sessions)

        def write(self, value):
            ts = time_stamp()
            if self.alert:
                self.alert_value(value)
            write_data(self.file, f"{ts},{value}")
        
        def alert_value(self, value):
            if value >= self.max_value or value <= self.min_value:
                log(LOG_FILE, "Data alert", "", telegram=True)

    class Sensor:

        _id_num = 1
        
        def __init__(self, model, stype, measure, sid=None):
            if not sid:
                self.id = f"sn0{self._id_num}" if self._id_num < 10 else f"sn{self._id_num}"
            else:
                self.id = sid
            self._id_num += 1
            self.model = model
            self.type = stype
            self.measure = measure
            self.onchange_session = None
            self.interval_sessions = {}

        def as_dict(self):
            d = {
                "id": self.id,
                "model": self.model,
                "type": self.type,
                "measure": self.measure,
            }
            return d

    def __init__(self, bid, ip, timec):
        self.id = bid
        self.ip = ip
        self.connection_date = timec
        self.sensors = {}
        self.url = f"http://{ip}:80/data"
        self.on_change_events = False
        self.sessions = []

    def new_sensor(self, model, stype, measure, sid=None):
        sensor = self.Sensor(model, stype, measure, sid=sid)
        self.sensors.update({model: sensor})

    # considerar session y sessionmanager fuera de la clase board
    def new_session(self, sensor, description, stype=None, interval_type=None, interval=None,
            start_date=None, finish_date=None,
            alert=False, min_value=None, max_value=None):
        session = Board.Session(self.id, sensor, description, stype,
            interval_type, interval, start_date,
            finish_date, alert, min_value, max_value
        )
        if description == 'onchange':
            self.sensors[sensor].onchange_session = session
        elif description == 'interval':
            self.sensors[sensor].interval_sessions.update({session.id: session})
        self.sessions.append(session)
        return session


    def set_ws(self, ws) -> None:
        self.ws_connection = ws

    def check_conn(self) -> None:
        if self.ws_connection:
            self.ws_connection.ping()

    def as_dict(self) -> dict:
        d = {
            "id": self.id,
            "ip": self.ip,
            "connection": self.connection_date,
            "url": self.url,
            "onchange_events": self.on_change_events,
            "sessions_len": len(self.sessions),
            "sensors": []
        }
        d['sensors'] = [ s.as_dict() for s in self.sensors.values() ]
        return d
    
    def sensors_list(self) -> list:
        return [s for s in self.sensors.values()]

    def get_data(self, sensor=None) -> int:
        res = None
        if sensor in self.sensors.keys():
            res = requests.get(self.url, params={"sensor": sensor}).text.split(':')
            return int(res[1])
        return None

    def save_board(self) -> None:
        if os.path.isfile(DEV_FILE) and not DEBUG:
            dev = read_json(DEV_FILE)
            dev['devices'].append(self.as_dict())            
            write_json(DEV_FILE, dev)

        elif not DEBUG:
            write_json(DEV_FILE, {"devices": [self.as_dict()]})
    
    def on_change(self, opt):
        self.on_change_events = opt
        option = 'sendon' if opt else 'sendoff'
        requests.get(f'{self.url}/config?option={option}')


####################
# Tornado Handlers #
####################

# Client Handlers

class MainHandler(RequestHandler):

    def get(self):
        
        devices = []
        for dev in BOARDS.values():
            devices.append(dev.as_dict())
        
        response = {
            "cronjobs": CronTab.jobs_exist(),
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


class InfoSession(RequestHandler):

    def initialize(self):
        self.board_id = self.get_argument('board', None)
        self.sensor_m = self.get_argument('sensor', None)
        self.session_id = self.get_argument('session', None)
    
    def get(self):
        sessions = read_json(SESS_FIL)
        session_list = []
        if self.board_id and not self.sensor_m:
            for session in sessions['sessions'].values():
                if session['board'] == self.board_id:
                    session_list.append(session)

        elif self.board_id and self.sensor_m:
            for session in sessions['sessions'].values():
                if session['board'] == self.board_id and session['sensor'] == self.sensor_m:
                    session_list.append(session)

        elif self.session_id:
            session_list.append(sessions[self.session_id])

        else:
            session_list = [ s for s in sessions['sessions'].value() ] if sessions['sessions'] else []

        self.write(json.dumps({"sessions": session_list}))


class DataSession(RequestHandler):

    def get(self, action):
        boardid = self.get_argument('board')
        #sensorid = self.get_argument('sensor')
        sessionid = self.get_argument('session')
        board = BOARDS[boardid]
        #sensor = board.sensors[sensorid]
        session = None
        for s in board.sessions:
            if s.id == sessionid:
                session = s

        if action == 'start':
            if session.description == 'onchange' and not board.on_change_events:
                board.on_change(True)

            url = "http://localhost:8000/data" if session.description == 'interval' else None
            session.start(url)

        elif action == 'finish':
            option = self.get_argument('option', None)
            session.finish()
            if option == 'clear':
                session_file = read_json(SESS_FIL)
                session_file['sessions'].pop(session.id)
                board.sessions.remove(session)
                os.remove(session.file)

    def post(self, board):
        """{
          "board":  str,
          "sensor": str,
          "session": {
              "type": "", open or scheduled
              "description": "interval" or "onchange",
              "interval_type": "", minute, hour, "day"
              "interval": int,
              "start_date": "", if start date is empty or null, the session start immediately
              "finish_date": "YYYY-MM-DD", only if defined session is True
              "alert": bool
              "min_value": None,
              "max_value": None
          }
        }"""
        print(self.request.body.decode())
        body = json.loads(self.request.body)
        session = body['session']
        board = BOARDS[board] if board in BOARDS.keys() else None
        sensor = board.sensors[body['sensor']]

        s = board.new_session(sensor.model, session['description'],
            stype=session['type'],
            interval_type=session['interval_type'],
            interval=session['interval'],
            start_date=session['start_date'],
            finish_date=session['finish_date'],
            alert=session['alert'],
            min_value=session['min_value'],
            max_value=session['max_value']
        )

        if not session['start_date']:
            url = "http://localhost:8000/data" if s.description == 'interval' else None
            s.start(url)
            if s.description == 'onchange':
                board.on_change(True)

        s.save_session()

    def put(self):
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
            if CronTab.jobs_exist():
                CronTab.clear_jobs()

        log(LOG_FILE, "alert", "Server stopped", telegram=True)
        sleep(0.5)
        IOLoop.current().stop()


# Cambiar
class GetData(RequestHandler):

    def get(self):

        board_name = self.get_argument("board")
        sensor_name = self.get_argument("sensor")
        session_id = self.get_argument("session")

        board = BOARDS[board_name]
        sensor = board.sensors[sensor_name]
        session = sensor.interval_sessions[session_id]

        value = board.get_data(sensor_name)
        session.write(value)


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
        CLNT_WS = self
        self.client_ip = self.request.remote_ip
        log(LOG_FILE, 'alert', f'Client IP {self.client_ip} connected', telegram=True)
        
        open_response = {
            "type": "open",
            "host": HOSTNAME,
            "devices": [],
            "version": get_version(),
        }
        for b in BOARDS.values():
            open_response['devices'].append(b.as_dict())
        
        self.write_message(open_response)

    def on_close(self):
        global CLNT_WS
        CLNT_WS = None
        log(LOG_FILE, 'alert', f'Client IP {self.client_ip} disconnected', telegram=True)

    def send_to_client(self, data):
        self.write_message(data)


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
            board = Board(self.id, self.device_ip, timestamp)
            for s in sens:
                t = self.get_argument(s).split(':')
                board.new_sensor(s, t[0], t[1])

            BOARDS.update({board.id: board})
            board.save_board()

        log(LOG_FILE, "alert", f"Device {self.id} IP {self.device_ip} is Connected", telegram=True)

    def on_message(self, message):
        global CLNT_WS
        print(message)
        data = message.split(':')
        sen = data[0]
        ivalue = int(data[1])
        board = BOARDS[self.id]
        sensor = board.sensors[sen]
        if sensor.onchange_session:
            sensor.onchange_session.write(ivalue)

        if CLNT_WS:
            CLNT_WS.send_to_client({
                "type": "value",
                "board": board.id,
                "sensor": sen,
                "value": ivalue
            })

    def on_close(self):
        log(LOG_FILE, "alert", f"Device {self.id} is Disconnected", telegram=True)
        print("Client Disconnected")

    def check_status(self):
        try:
            self.ping()
        except Exception:
            print('ex')


URLS = [
    (r"/", MainHandler),
    (r"/data", GetData),
    (r"/config/telegram", TelegramConfig),
    (r"/server/stop", SafeStop),
    (r"/ws/board", WebsocketDataListener),
    (r"/ws/client", WebsocketClientHandler),
    (r"/session/action/([^/]+)", DataSession),
    (r"/session/info", InfoSession)
    ]


def main():

    # Creación de directorios y archivos
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR)
    if not os.path.isdir(SESS_DIR):
        os.makedirs(SESS_DIR)    

    if not os.path.isfile(LOG_FILE):
        with open(LOG_FILE, 'w+') as f:
            f.write("TimeStamp, Type, Message\n")
        f.close()
    if not os.path.isfile(SESS_FIL):
        write_json(SESS_FIL, {"sessions":{}})


    # chequea si existe archivo con dispositivos
    if os.path.isfile(DEV_FILE):
        devices = read_json(DEV_FILE)   
        for d in devices['devices']:
            board = Board(d['id'], d['ip'], d['connection_date'])
            board.new_sensor(
                d['sensors']['model'],
                d['sensors']['type'],
                d['sensors']['measure'],
                sid=d['sensors']['id']
            )
            BOARDS.update({board.id: board})

    # chequea sesiones


    #"auto update" cada lunes a las 00:01
    if not DEBUG and not CronTab.job_exist(f"{BASE_DIR}/tc_cli.py update"):
        job = CronTab.new_job(f"{BASE_DIR}/tc_cli.py update")
        job.day_of_week = 1
        job.minute = 1
        CronTab.write()

    # Inicio del servidor
    app = Application(URLS)
    server = HTTPServer(app)
    server.listen(8000)
    log(LOG_FILE, "alert", "Server started", telegram=True)
    IOLoop.current().start()


if __name__ == '__main__':
    main()