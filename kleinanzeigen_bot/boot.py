# SPDX-License-Identifier: AGPL-3.0-or-later
"""Start the isolated desktop and web services; shut down if a service fails."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

os.umask(0o077)
options_path = Path('/data/options.json')
options = json.loads(options_path.read_text()) if options_path.exists() else {}
for path in ['/data/workspace', '/data/home', '/data/home/.cache', '/data/state']:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    os.chown(p, 1000, 1000)
env = dict(os.environ, HOME='/data/home', DISPLAY=':99',
           JOB_TIMEOUT_MINUTES=str(options.get('job_timeout_minutes', 30)))
# Supervisor credentials must not reach the browser or child processes.
env.pop('SUPERVISOR_TOKEN', None)
prefix = ['setpriv', '--reuid=1000', '--regid=1000', '--init-groups']
children = []
stopping = False

def stop(_sig=None, _frame=None):
    global stopping
    stopping = True

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

def launch(args, unprivileged=True):
    p = subprocess.Popen((prefix if unprivileged else []) + args, env=env)
    children.append(p)
    return p

exit_code = 0
try:
    width = int(options.get('desktop_width', 1440))
    height = int(options.get('desktop_height', 900))
    launch(['Xvfb', ':99', '-screen', '0', f'{width}x{height}x24', '-nolisten', 'tcp', '-ac'])
    for _ in range(100):
        probe = subprocess.run(prefix + ['xdpyinfo', '-display', ':99'], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            break
        if stopping or children[0].poll() is not None:
            raise RuntimeError('Xvfb konnte nicht gestartet werden')
        time.sleep(0.1)
    else:
        raise RuntimeError('Xvfb-Startzeit überschritten')
    launch(['openbox', '--sm-disable'])
    # Only loopback; access is authenticated by Home Assistant ingress.
    launch(['x11vnc', '-display', ':99', '-localhost', '-rfbport', '5900',
            '-forever', '-shared', '-nopw', '-quiet'])
    launch(['websockify', '--web=/usr/share/novnc', '127.0.0.1:6080', '127.0.0.1:5900'])
    launch(['/usr/bin/python3', '/opt/ha-bot/app/server.py'])
    launch(['nginx', '-g', 'daemon off;'], unprivileged=False)
    print('Kleinanzeigen-Web-GUI gestartet. Zugriff über Home Assistant Ingress.', flush=True)
    while not stopping:
        for child in children:
            if child.poll() is not None:
                raise RuntimeError(f'Dienst beendet: PID {child.pid}, Code {child.returncode}')
        time.sleep(0.5)
except Exception as exc:
    print(f'Start-/Laufzeitfehler: {exc}', file=sys.stderr, flush=True)
    exit_code = 1
finally:
    # The web server receives SIGTERM first so it can stop its current bot job.
    for child in reversed(children):
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + 12
    for child in reversed(children):
        try:
            child.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
sys.exit(exit_code)
