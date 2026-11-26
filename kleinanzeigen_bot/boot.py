# SPDX-License-Identifier: AGPL-3.0-or-later
"""Supervise X11, desktop and ingress. Preserve state ownership on upgrades."""
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
# Existing v0.1.0 nested root-owned files must be writable by UID 1000 too.
for folder in ['/data/workspace', '/data/home', '/data/state']:
    p = Path(folder)
    p.mkdir(parents=True, exist_ok=True)
    os.chown(p, 1000, 1000)
    for parent, directories, files in os.walk(p, followlinks=False):
        for name in directories + files:
            q = Path(parent)/name
            if not q.is_symlink():
                os.chown(q, 1000, 1000)
env = dict(os.environ, HOME='/data/home', DISPLAY=':99',
           JOB_TIMEOUT_MINUTES=str(options.get('job_timeout_minutes',30)))
env.pop('SUPERVISOR_TOKEN', None)
prefix = ['setpriv','--reuid=1000','--regid=1000','--init-groups']
children, stopping = [], False

def stop(*_):
    global stopping
    stopping = True

signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)

def launch(args, unprivileged=True):
    p = subprocess.Popen((prefix if unprivileged else [])+args, env=env)
    children.append(p)
    return p

exit_code = 0
try:
    width = max(1280,int(options.get('desktop_width',1440)))
    height = max(800,int(options.get('desktop_height',900)))
    launch(['Xvfb',':99','-screen','0',f'{width}x{height}x24','-nolisten','tcp','-ac'])
    for _ in range(100):
        probe = subprocess.run(prefix+['xdpyinfo','-display',':99'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            break
        if stopping or children[0].poll() is not None:
            raise RuntimeError('Xvfb konnte nicht gestartet werden')
        time.sleep(.1)
    else:
        raise RuntimeError('Xvfb-Startzeit überschritten')
    launch(['openbox','--sm-disable'])
    launch(['x11vnc','-display',':99','-localhost','-rfbport','5900','-forever','-shared','-nopw','-quiet'])
    launch(['websockify','--web=/usr/share/novnc','127.0.0.1:6080','127.0.0.1:5900'])
    launch(['/opt/venv/bin/python','/opt/ha-bot/app/server.py'])
    launch(['nginx','-g','daemon off;'],unprivileged=False)
    print('Kleinanzeigen 0.2.0: GUI und Scheduler gestartet; Zugriff über HA Ingress.',flush=True)
    while not stopping:
        for child in children:
            if child.poll() is not None:
                raise RuntimeError(f'Dienst beendet: PID {child.pid}, Code {child.returncode}')
        time.sleep(.5)
except Exception as exc:
    print(f'Start-/Laufzeitfehler: {exc}',file=sys.stderr,flush=True)
    exit_code = 1
finally:
    # Give the web worker time to stop its isolated bot/browser process group
    # while the desktop is still alive. nginx is stopped first.
    for child in reversed(children):
        if child.poll() is None:
            child.terminate()
        try:
            child.wait(timeout=12 if child.args[-1] == '/opt/ha-bot/app/server.py' else 4)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
sys.exit(exit_code)
