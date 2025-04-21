# app.py

import os
import re
import subprocess
import threading
import json
import configparser
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

# --- Load settings from settings.conf ---
CONFIG_PATH = "settings.conf"
LOG_FILE    = "castletracker.log"

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

# état partagé
TRANSFER_STATS = {
    'total_size':         0,   # octets totaux sur la source
    'remote_count':       0,   # nombre de fichiers source
    'transferred_bytes':  0,
    'overall_pct':        0,
    'speed_bps':          0,
    'eta':                '',
    'elapsed':            '',
}

# regex pour la ligne Transferred: …, XX%, 18.900 MiB/s, ETA 7m19s
GLOBAL_RE = re.compile(
    r"Transferred:\s*([\d.]+)\s*(MiB|GiB|KiB|B)\s*/\s*([\d.]+)\s*(MiB|GiB|KiB|B)"
    r",\s*(\d+)%\s*,\s*([\d.]+)\s*(KiB|MiB|GiB|B)/s\s*,\s*ETA\s*(\S+)"
)
# regex pour Elapsed time: 15.5s
ELAPSED_RE = re.compile(r"Elapsed time:\s*([0-9\.hms]+)")

# conversion en octets
UNIT_MAP = {
    'B':   1,
    'KiB': 1024,
    'MiB': 1024**2,
    'GiB': 1024**3,
}

def write_log(entry):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {entry}\n")

def build_rclone_args(path):
    obsc = subprocess.run(
        [RCLONE_EXE, 'obscure', REMOTE_PASS],
        capture_output=True, text=True
    ).stdout.strip()
    return [
        f":sftp:{path}",
        '--sftp-host', REMOTE_HOST,
        '--sftp-user', REMOTE_USER,
        '--sftp-port', RCLONE_PORT,
        '--sftp-pass', obsc
    ]

def get_local_stats(local_path):
    total_size = 0
    total_files = 0
    for dirpath, _, filenames in os.walk(local_path):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            if os.path.isfile(fp):
                total_files += 1
                total_size += os.path.getsize(fp)
    return total_files, total_size

@app.route("/", methods=["GET", "POST"])
def index():
    global LOCAL_TARGET, REMOTE_PATH
    if request.method == "POST":
        LOCAL_TARGET = request.form['local_path']
        REMOTE_PATH  = request.form['remote_path']
        return redirect(url_for('index'))
    return render_template(
        "index.html",
        stats=TRANSFER_STATS,
        local_path=LOCAL_TARGET,
        remote_path=REMOTE_PATH
    )

@app.route("/transfer", methods=["POST"])
def transfer():
    global LOCAL_TARGET, REMOTE_PATH
    REMOTE_PATH  = request.form['remote_path']
    LOCAL_TARGET = request.form['local_path']
    # réinitialiser l'état
    TRANSFER_STATS.update({
        'transferred_bytes':  0,
        'overall_pct':        0,
        'speed_bps':          0,
        'eta':                '',
        'elapsed':            '',
        'total_size':         0,
        'remote_count':       0,
    })
    threading.Thread(target=rclone_thread, daemon=True).start()
    return redirect(url_for('index'))

@app.route("/progress")
def progress():
    local_count, local_bytes = get_local_stats(LOCAL_TARGET)
    return jsonify({
        'percent':               TRANSFER_STATS['overall_pct'],
        'speed':                 f"{TRANSFER_STATS['speed_bps'] / 1024**2:.2f} MiB/s",
        'eta':                   TRANSFER_STATS['eta'],
        'elapsed':               TRANSFER_STATS['elapsed'],
        'remote_count':          TRANSFER_STATS['remote_count'],
        'remote_total_bytes':    TRANSFER_STATS['total_size'],
        'local_count':           local_count,
        'local_total_bytes':     local_bytes,
    })

def rclone_thread():
    # scanner la source pour taille et nombre de fichiers
    args = build_rclone_args(REMOTE_PATH)
    ls = subprocess.run([RCLONE_EXE, 'lsjson'] + args,
                        capture_output=True, text=True)
    try:
        files = json.loads(ls.stdout)
        TRANSFER_STATS['total_size']   = sum(f.get('Size',0) for f in files)
        TRANSFER_STATS['remote_count'] = len(files)
    except:
        pass

    # lancer le copy avec stats chaque seconde
    cmd = [
        RCLONE_EXE, 'copy',
        *args,
        LOCAL_TARGET,
        '--stats', '1s',
        '--log-level', 'INFO'
    ]
    write_log("CMD: " + " ".join(cmd))
    proc = subprocess.Popen(cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True)

    for raw in proc.stdout:
        line = raw.strip()
        # stats globales
        m = GLOBAL_RE.search(line)
        if m:
            tv, tu, totv, totu, pct, sv, su, eta = m.groups()
            transferred = float(tv) * UNIT_MAP[tu]
            TRANSFER_STATS['transferred_bytes'] = int(transferred)
            TRANSFER_STATS['overall_pct']       = int(pct)
            TRANSFER_STATS['speed_bps']         = float(sv) * UNIT_MAP[su]
            TRANSFER_STATS['eta']               = eta
        # elapsed
        me = ELAPSED_RE.search(line)
        if me:
            TRANSFER_STATS['elapsed'] = me.group(1)

    TRANSFER_STATS['overall_pct'] = 100
    write_log("Transfer complete")

if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
