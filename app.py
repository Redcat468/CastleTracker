
import os
import re
import subprocess
import threading
import json
import configparser
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, send_from_directory
)
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet

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

TRANSFER_STATS = {
    'files':              [],   # list of {'Path', 'Size'}
    'total_size':         0,
    'remote_count':       0,
    'transferred_bytes':  0,
    'overall_pct':        0,
    'speed_bps':          0,
    'eta':                '',
    'elapsed':            '',
    'start_time':         None,
    'end_time':           None,
}

# Regex patterns
GLOBAL_RE = re.compile(
    r"Transferred:\s*([\d.]+)\s*(MiB|GiB|KiB|B)\s*/\s*([\d.]+)\s*(MiB|GiB|KiB|B)"
    r",\s*(\d+)%\s*,\s*([\d.]+)\s*(KiB|MiB|GiB|B)/s\s*,\s*ETA\s*(\S+)"
)
ELAPSED_RE = re.compile(r"Elapsed time:\s*([0-9\.hms]+)")
UNIT_MAP   = {'B':1, 'KiB':1024, 'MiB':1024**2, 'GiB':1024**3}


def write_log(entry):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {entry}\n")


def build_rclone_args(path):
    obsc = subprocess.run([
        RCLONE_EXE, 'obscure', REMOTE_PASS
    ], capture_output=True, text=True).stdout.strip()
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

    # Reset stats
    TRANSFER_STATS.update({
        'files': [],
        'total_size': 0,
        'remote_count': 0,
        'transferred_bytes': 0,
        'overall_pct': 0,
        'speed_bps': 0,
        'eta': '',
        'elapsed': '',
        'start_time': datetime.now(),
        'end_time': None
    })

    threading.Thread(target=rclone_thread, daemon=True).start()
    return redirect(url_for('index'))


@app.route("/new", methods=["POST"])
def new_transfer():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fn = f"report_{ts}.pdf"
    path = os.path.join(REPORT_DIR, fn)

    doc = SimpleDocTemplate(path, pagesize=letter)
    styles = getSampleStyleSheet()
    elems = []

    # Title
    elems.append(Paragraph("Rapport de Transfert", styles['Title']))
    elems.append(Spacer(1, 12))

    # Timestamps
    start = TRANSFER_STATS['start_time'].strftime("%Y-%m-%d %H:%M:%S")
    end = TRANSFER_STATS['end_time'].strftime("%Y-%m-%d %H:%M:%S") if TRANSFER_STATS['end_time'] else '-'
    elems.append(Paragraph(f"Début: {start}  |  Fin: {end}", styles['Normal']))
    elems.append(Spacer(1, 12))

    # Summary table: Source vs Destination
    local_count, local_bytes = get_local_stats(LOCAL_TARGET)
    summary_data = [
        ["", "Source", "Destination"],
        ["NB de fichiers", TRANSFER_STATS['remote_count'], local_count],
        ["Taille (octets)", TRANSFER_STATS['total_size'], local_bytes],
        ["Taille (Go)", f"{TRANSFER_STATS['total_size']/1e9:.2f}", f"{local_bytes/1e9:.2f}"],
        ["Vitesse moyenne (MiB/s)", f"{TRANSFER_STATS['speed_bps']/1024**2:.2f}", ""],
        ["Temps écoulé", TRANSFER_STATS['elapsed'], ""]
    ]
    t = Table(summary_data, hAlign='LEFT', colWidths=[150, 100, 100])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID',       (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
    ]))
    elems.append(t)
    elems.append(Spacer(1, 24))

    # Files table
    elems.append(Paragraph("Détails des fichiers transférés", styles['Heading2']))
    elems.append(Spacer(1, 12))
    files_data = [['Chemin', 'Taille (octets)']] + [
        [f['Path'], f['Size']] for f in TRANSFER_STATS['files']
    ]
    tf = Table(files_data, hAlign='LEFT', colWidths=[350, 120])
    tf.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID',       (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
    ]))
    elems.append(tf)

    doc.build(elems)

    # Reset for next transfer
    TRANSFER_STATS.update({
        'files': [],
        'total_size': 0,
        'remote_count': 0,
        'transferred_bytes': 0,
        'overall_pct': 0,
        'speed_bps': 0,
        'eta': '',
        'elapsed': '',
        'start_time': None,
        'end_time': None
    })

    return redirect(url_for('download_report', filename=fn))


@app.route('/reports/<filename>')
def download_report(filename):
    return send_from_directory(REPORT_DIR, filename, as_attachment=True)


@app.route("/progress")
def progress():
    local_count, local_bytes = get_local_stats(LOCAL_TARGET)
    return jsonify({
        'percent':            TRANSFER_STATS['overall_pct'],
        'speed':              f"{TRANSFER_STATS['speed_bps']/1024**2:.2f} MiB/s",
        'eta':                TRANSFER_STATS['eta'],
        'elapsed':            TRANSFER_STATS['elapsed'],
        'remote_count':       TRANSFER_STATS['remote_count'],
        'remote_total_bytes': TRANSFER_STATS['total_size'],
        'local_count':        local_count,
        'local_total_bytes':  local_bytes,
    })


def rclone_thread():
    TRANSFER_STATS['start_time'] = datetime.now()
    args = build_rclone_args(REMOTE_PATH)
    ls = subprocess.run([RCLONE_EXE, 'lsjson'] + args,
                        capture_output=True, text=True)
    try:
        files = json.loads(ls.stdout)
        TRANSFER_STATS['files']       = [
            {'Path': f['Path'], 'Size': f.get('Size', 0)}
            for f in files
        ]
        TRANSFER_STATS['total_size']  = sum(f.get('Size', 0) for f in files)
        TRANSFER_STATS['remote_count']= len(files)
    except Exception:
        pass

    cmd = [RCLONE_EXE, 'copy', *args, LOCAL_TARGET,
           '--stats', '1s', '--log-level', 'INFO']
    write_log("CMD: " + " ".join(cmd))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    for raw in proc.stdout:
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
    write_log("Transfer complete")


if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")

