import os
import re
import subprocess
import threading
import json
import configparser
from datetime import datetime
from flask import Flask, render_template, jsonify, send_from_directory
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from flask import redirect, url_for


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
REPORT_DIR = os.path.join(BASE_DIR, 'reports')


app = Flask(__name__)

# --- Load settings ---
CONFIG_PATH = "settings.conf"
LOG_FILE    = "castletracker.log"
REPORT_DIR  = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

RCLONE_EXE     = os.path.abspath(config['paths']['rclone_path'])
REMOTE_USER    = config['remote']['user']
REMOTE_HOST    = config['remote']['host']
DEFAULT_REMOTE = config['remote']['path']
REMOTE_PASS    = config['remote']['password']
RCLONE_PORT    = config['remote'].get('port', '22')
DEFAULT_LOCAL  = config['local']['default_path']

LOCAL_TARGET = DEFAULT_LOCAL
REMOTE_PATH  = DEFAULT_REMOTE

# Control creation of subprocess windows on Windows
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

# Global process handle for stopping transfer
TRANSFER_PROC = None

# Shared state
TRANSFER_STATS = {
    'status': 'idle',
    'files': [],
    'total_size': 0,
    'remote_count': 0,
    'local_count': 0,
    'local_total_bytes': 0,
    'transferred_bytes': 0,
    'overall_pct': 0,
    'speed_bps': 0,
    'eta': '',
    'elapsed': '',
    'start_time': None,
    'end_time': None,
}

# Regex for parsing rclone copy output
GLOBAL_RE = re.compile(
    r"Transferred:\s*([\d.]+)\s*(MiB|GiB|KiB|B)\s*/\s*([\d.]+)\s*(MiB|GiB|KiB|B)"
    r",\s*(\d+)%\s*,\s*([\d.]+)\s*(KiB|MiB|GiB|B)/s\s*,\s*ETA\s*(\S+)"
)
ELAPSED_RE = re.compile(r"Elapsed time:\s*([0-9\.hms]+)")
UNIT_MAP   = {'B':1, 'KiB':1024, 'MiB':1024**2, 'GiB':1024**3}

# Optimization flags
OPTIM_FLAGS = [
    '--sftp-disable-hashcheck',
    '--sftp-set-modtime=false',
    '--multi-thread-streams=4',
    '--multi-thread-cutoff=50M',
    '--transfers=8',
    '--checkers=16',
    '--buffer-size=64M',
    '--timeout=30s',
    '--contimeout=15s'
]


def write_log(entry):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {entry}\n")


def build_rclone_args(path):
    obsc = subprocess.run(
        [RCLONE_EXE, 'obscure', REMOTE_PASS],
        capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW
    ).stdout.strip()
    return [
        f":sftp:{path}",
        '--sftp-host', REMOTE_HOST,
        '--sftp-user', REMOTE_USER,
        '--sftp-port', RCLONE_PORT,
        '--sftp-pass', obsc
    ]


def get_local_stats(local_path):
    total_size, total_files = 0, 0
    for dp, _, fns in os.walk(local_path):
        for fn in fns:
            fp = os.path.join(dp, fn)
            if os.path.isfile(fp):
                total_files += 1
                total_size += os.path.getsize(fp)
    return total_files, total_size

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', stats=TRANSFER_STATS)

@app.route('/scan', methods=['POST'])
def scan():
    # Remote totals via rclone size
    rargs = build_rclone_args(REMOTE_PATH)
    size_cmd = [RCLONE_EXE, 'size', '--json'] + rargs
    write_log(f"CMD: {' '.join(size_cmd)}")
    sr = subprocess.run(
        size_cmd, capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW
    )
    try:
        js = json.loads(sr.stdout)
        TRANSFER_STATS['total_size']   = js.get('bytes', 0)
        TRANSFER_STATS['remote_count'] = js.get('count', 0)
    except Exception:
        TRANSFER_STATS['total_size'] = 0
        TRANSFER_STATS['remote_count'] = 0

    # Local totals via os.walk
    lc, lb = get_local_stats(LOCAL_TARGET)
    TRANSFER_STATS['local_count']       = lc
    TRANSFER_STATS['local_total_bytes'] = lb

    # Fetch full file list for PDF
    list_cmd = [RCLONE_EXE, 'lsjson', '--recursive'] + rargs
    write_log(f"CMD: {' '.join(list_cmd)}")
    lr = subprocess.run(
        list_cmd, capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW
    )
    try:
        files = json.loads(lr.stdout)
        TRANSFER_STATS['files'] = [{'Path': f['Path'], 'Size': f.get('Size',0)} for f in files]
    except Exception:
        TRANSFER_STATS['files'] = []

    return ('', 204)

@app.route('/transfer', methods=['POST'])
def transfer():
    # Reset stats and set running
    for k in list(TRANSFER_STATS.keys()):
        TRANSFER_STATS[k] = 0 if isinstance(TRANSFER_STATS[k], (int, float)) else None
    TRANSFER_STATS.update({
        'files': [], 'eta': '', 'elapsed': '',
        'start_time': datetime.now(), 'end_time': None,
        'status': 'running'
    })
    threading.Thread(target=rclone_thread, daemon=True).start()
    return ('', 204)

@app.route('/stop', methods=['POST'])
def stop_transfer():
    global TRANSFER_PROC
    if TRANSFER_PROC and TRANSFER_PROC.poll() is None:
        TRANSFER_PROC.kill()
        TRANSFER_STATS['status'] = 'stopped'
    return ('', 204)

@app.route('/resetsource', methods=['POST'])
def reset_source():
    # Delete all files under remote:path, then empty subdirs, preserve root
    rargs = build_rclone_args(REMOTE_PATH)
    # delete files
    subprocess.run(
        [RCLONE_EXE, 'delete', *rargs], capture_output=True,
        creationflags=CREATE_NO_WINDOW
    )
    # remove empty directories
    subprocess.run(
        [RCLONE_EXE, 'rmdirs', *rargs], capture_output=True,
        creationflags=CREATE_NO_WINDOW
    )
    # Reset stats
    for k in list(TRANSFER_STATS.keys()):
        TRANSFER_STATS[k] = 0 if isinstance(TRANSFER_STATS[k], (int, float)) else None
    TRANSFER_STATS.update({'files': [], 'eta': '', 'elapsed': '', 'status': 'idle'})
    return ('', 204)


@app.route('/progress')
def progress():
    # Live update local stats
    lc, lb = get_local_stats(LOCAL_TARGET)
    TRANSFER_STATS['local_count']       = lc
    TRANSFER_STATS['local_total_bytes'] = lb
    return jsonify({
        'status':             TRANSFER_STATS['status'],
        'percent':            TRANSFER_STATS['overall_pct'],
        'speed':              f"{TRANSFER_STATS['speed_bps']/1024**2:.2f} MiB/s",
        'eta':                TRANSFER_STATS['eta'],
        'elapsed':            TRANSFER_STATS['elapsed'],
        'remote_count':       TRANSFER_STATS['remote_count'],
        'remote_total_bytes': TRANSFER_STATS['total_size'],
        'local_count':        TRANSFER_STATS['local_count'],
        'local_total_bytes':  TRANSFER_STATS['local_total_bytes'],
    })

def rclone_thread():
    global TRANSFER_PROC
    scan()
    args = build_rclone_args(REMOTE_PATH)
    cmd = [RCLONE_EXE, 'copy', *args, LOCAL_TARGET, '--stats', '1s', '--log-level', 'INFO'] + OPTIM_FLAGS
    write_log("CMD: " + " ".join(cmd))
    TRANSFER_PROC = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, creationflags=CREATE_NO_WINDOW
    )
    for raw in TRANSFER_PROC.stdout:
        line = raw.strip()
        m = GLOBAL_RE.search(line)
        if m:
            tv, tu, _, _, pct, sv, su, eta = m.groups()
            TRANSFER_STATS['transferred_bytes'] = int(float(tv) * UNIT_MAP[tu])
            TRANSFER_STATS['overall_pct']       = int(pct)
            TRANSFER_STATS['speed_bps']         = float(sv) * UNIT_MAP[su]
            TRANSFER_STATS['eta']               = eta
        me = ELAPSED_RE.search(line)
        if me:
            TRANSFER_STATS['elapsed'] = me.group(1)
    TRANSFER_STATS['end_time'] = datetime.now()
    TRANSFER_STATS['overall_pct'] = 100
    TRANSFER_STATS['status'] = 'done'
    write_log("Transfer complete")

if __name__ == '__main__':
    app.run(debug=True, port=12000, host='0.0.0.0')
