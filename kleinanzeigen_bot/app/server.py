# SPDX-License-Identifier: AGPL-3.0-or-later
"""Home Assistant ingress UI for the upstream CLI. No shell command execution."""
from collections import deque
import codecs
import errno
import json
import os
from pathlib import Path
import pty
import re
import secrets
import select
import signal
import subprocess
import threading
import time
import uuid
from flask import Flask, abort, jsonify, render_template, request, send_file
import yaml
from werkzeug.exceptions import HTTPException

WORK = Path(os.environ.get('BOT_WORKSPACE', '/data/workspace')).resolve()
STATE = Path(os.environ.get('BOT_STATE', '/data/state')).resolve()
BIN = os.environ.get('BOT_BINARY', '/usr/local/bin/kleinanzeigen-bot')
TIMEOUT = int(os.environ.get('JOB_TIMEOUT_MINUTES', '30')) * 60
MAX_TEXT = 1024 * 1024
MAX_LOG = 1024 * 1024
CSRF = secrets.token_urlsafe(32)
LOCK = threading.RLock()
app = Flask(__name__, template_folder=str(Path(__file__).parent / 'templates'))
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
current = None
history = []
DEFAULT_CONFIG = """login:
  username: "${KLEINANZEIGEN_BOT_USERNAME}"
  password: "${KLEINANZEIGEN_BOT_PASSWORD}"
ad_files:
  - "./ads/**/*.{yaml,yml,json}"
  - "./downloaded-ads/**/*.{yaml,yml,json}"
download:
  dir: ./downloaded-ads
browser:
  user_data_dir: /data/workspace/browser-profile
  use_private_window: false
  arguments:
    - --no-sandbox
    - --disable-dev-shm-usage
"""
COMMANDS = {
    'verify': None, 'status': None, 'list': None, 'diagnose': None,
    'version': None, 'help': None, 'login': None,
    'publish': {'all', 'due', 'new', 'changed'},
    'download': {'all', 'new', 'drafts'},
    'update': {'all', 'changed'}, 'extend': {'all'},
    'reserve': {'all'}, 'activate': {'all'}, 'delete': {'all', 'due'},
}
MUTATING = {'publish', 'update', 'extend', 'reserve', 'activate', 'delete'}

def atomic_write(path, text):
    tmp = path.with_name(path.name + '.tmp-' + secrets.token_hex(4))
    try:
        with tmp.open('x', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.chmod(0o600)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def initialize():
    global history
    os.umask(0o077)
    for p in [WORK, STATE, WORK / 'ads', WORK / 'ads/images', WORK / 'downloaded-ads']:
        p.mkdir(parents=True, exist_ok=True)
    if not (WORK / 'config.yaml').exists():
        atomic_write(WORK / 'config.yaml', DEFAULT_CONFIG)
    h = STATE / 'history.json'
    if h.exists():
        try:
            history = json.loads(h.read_text())[-50:]
            for job in history:
                if job['state'] == 'running':
                    job.update(state='interrupted', ended=time.time(), returncode=None)
            atomic_write(h, json.dumps(history, ensure_ascii=False))
        except (ValueError, KeyError, TypeError):
            history = []


def parse_mapping(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_TEXT:
        abort(400, 'Text fehlt oder überschreitet 1 MiB.')
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError:
        abort(400, 'Ungültiges YAML/JSON. Syntax im Editor prüfen.')
    if not isinstance(value, dict):
        abort(400, 'Die Datei muss ein YAML/JSON-Objekt enthalten.')
    return value


def editable_path(name):
    if not isinstance(name, str) or not name or '\\' in name:
        abort(400, 'Ungültiger Dateipfad.')
    parts = Path(name).parts
    if Path(name).is_absolute() or '..' in parts or any(p.startswith('.') for p in parts):
        abort(400, 'Ungültiger Dateipfad.')
    if parts[0] not in {'ads', 'downloaded-ads'} or len(parts) < 2:
        abort(400, 'Nur Dateien unter ads/ oder downloaded-ads/ sind erlaubt.')
    p = WORK / name
    if p.suffix.lower() not in {'.yaml', '.yml', '.json', '.draft'}:
        abort(400, 'Nur YAML-, JSON- und Draft-Dateien sind editierbar.')
    walk = WORK
    for part in parts:
        walk = walk / part
        if walk.is_symlink():
            abort(400, 'Symbolische Links sind nicht erlaubt.')
    if not p.resolve().is_relative_to(WORK):
        abort(400, 'Datei liegt außerhalb des Arbeitsverzeichnisses.')
    return p


def idle_required():
    if current is not None and current['state'] == 'running':
        abort(409, 'Ein Bot-Auftrag läuft. Zuerst abschließen oder stoppen.')


def backup(path):
    if path.exists():
        directory = STATE / 'backups'
        directory.mkdir(exist_ok=True)
        key = str(path.relative_to(WORK)).replace('/', '__')
        atomic_write(directory / f'{key}.{time.time_ns()}.bak', path.read_text())
        for old in sorted(directory.glob(key + '.*.bak'))[:-10]:
            old.unlink()


def credentials():
    p = WORK / '.credentials.json'
    return json.loads(p.read_text()) if p.exists() else {}


def redact(text, secret_values):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    for value in sorted((v for v in secret_values if v), key=len, reverse=True):
        text = text.replace(value, '[VERBORGEN]')
    return text


def persist_history():
    atomic_write(STATE / 'history.json', json.dumps(history[-50:], ensure_ascii=False))


def public_job(job):
    return {k: job.get(k) for k in ['id', 'command', 'selector', 'state', 'started', 'ended', 'returncode']}


def validate_job(data):
    command = data.get('command')
    if command not in COMMANDS:
        abort(400, 'Unbekannter Befehl.')
    allowed = COMMANDS[command]
    selector = data.get('selector', '')
    if not isinstance(selector, str):
        abort(400, 'Ungültige Anzeigenauswahl.')
    if allowed is not None:
        selectors = selector.split(',')
        if not selector or not all(s in allowed or re.fullmatch(r'[0-9]+', s) for s in selectors):
            abort(400, 'Anzeigenauswahl nicht für diesen Befehl erlaubt.')
        if command != 'publish' and len(selectors) > 1 and not all(s.isdigit() for s in selectors):
            abort(400, 'Mehrfachauswahl hier nur mit Anzeigen-IDs erlaubt.')
    elif selector:
        abort(400, 'Dieser Befehl verwendet keine Anzeigenauswahl.')
    if command in MUTATING and data.get('confirm') is not True:
        abort(400, 'Änderungen am Kleinanzeigen-Konto müssen bestätigt werden.')
    args = [BIN, command, '--workspace-mode=portable', f'--config={WORK / "config.yaml"}',
            f'--logfile={WORK / "bot.log"}', '--lang=de']
    if allowed is not None:
        args.append('--ads=' + selector)
    if data.get('keep_old') is True and command == 'publish':
        args.append('--keep-old')
    return command, selector, args


def kill_group(process, sig):
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def run_job(job, args):
    master = slave = None
    process = None
    end_state = 'failed'
    try:
        saved = credentials()
        config = yaml.safe_load((WORK / 'config.yaml').read_text()) or {}
        login = config.get('login', {})
        hidden = [saved.get('password', ''), saved.get('username', '')]
        hidden += [v for v in login.values() if isinstance(v, str) and not v.startswith('${')]
        env = dict(os.environ)
        env.pop('SUPERVISOR_TOKEN', None)
        env.update(KLEINANZEIGEN_BOT_USERNAME=saved.get('username', ''),
                   KLEINANZEIGEN_BOT_PASSWORD=saved.get('password', ''), TERM='dumb', NO_COLOR='1')
        master, slave = pty.openpty()
        process = subprocess.Popen(args, cwd=WORK, env=env, stdin=slave, stdout=slave,
                                   stderr=slave, start_new_session=True, close_fds=True)
        os.close(slave)
        slave = None
        with LOCK:
            job['process'] = process
            job['pty'] = master
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        deadline = time.monotonic() + TIMEOUT
        termination_at = None
        overlap = max([len(s) for s in hidden if s] + [1])
        pending = ''
        def append(chunk, final=False):
            nonlocal pending
            pending += chunk
            if final:
                output, pending = pending, ''
            elif len(pending) > overlap * 2:
                cut = len(pending) - overlap
                for secret in hidden:
                    if secret:
                        start = pending.rfind(secret, 0, min(len(pending), cut + len(secret)))
                        if start >= 0 and start < cut < start + len(secret):
                            cut = start
                output, pending = pending[:cut], pending[cut:]
            else:
                return
            with LOCK:
                job['chunks'].append(redact(output, hidden))
        while True:
            with LOCK:
                requested = job['stop_requested']
            timed_out = time.monotonic() >= deadline
            if (requested or timed_out) and termination_at is None:
                end_state = 'stopped' if requested else 'timeout'
                kill_group(process, signal.SIGTERM)
                termination_at = time.monotonic()
            if termination_at is not None and time.monotonic() - termination_at > 5:
                kill_group(process, signal.SIGKILL)
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    raw = os.read(master, 8192)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        break
                    raise
                if not raw:
                    break
                append(decoder.decode(raw))
            elif process.poll() is not None:
                break
        append(decoder.decode(b'', final=True), final=True)
        try:
            code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            kill_group(process, signal.SIGKILL)
            code = process.wait(timeout=5)
        if termination_at is None:
            end_state = 'success' if code == 0 else 'failed'
        with LOCK:
            job['returncode'] = code
    except Exception as exc:
        with LOCK:
            job['chunks'].append(f'\nAuftrag konnte nicht abgeschlossen werden: {type(exc).__name__}\n')
        if process is not None:
            kill_group(process, signal.SIGKILL)
            process.wait(timeout=5)
    finally:
        if process is not None:
            kill_group(process, signal.SIGTERM)
        with LOCK:
            job['pty'] = None
            for fd in [master, slave]:
                if fd is not None:
                    os.close(fd)
            job.update(state=end_state, ended=time.time())
            atomic_write(STATE / (job['id'] + '.log'), ''.join(job['chunks'])[-MAX_LOG:])
            history[:] = [h for h in history if h['id'] != job['id']]
            history.append(public_job(job))
            while len(history) > 50:
                removed = history.pop(0)
                (STATE / (removed['id'] + '.log')).unlink(missing_ok=True)
            persist_history()
            (WORK / 'bot.log').unlink(missing_ok=True)


@app.before_request
def protect():
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        if not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), CSRF):
            abort(403, 'Sicherheitstoken fehlt. Oberfläche neu laden.')
        if not request.is_json and request.path != '/api/images':
            abort(415, 'JSON erwartet.')
        if request.is_json and not isinstance(request.get_json(), dict):
            abort(400, 'Ein JSON-Objekt wird erwartet.')


@app.errorhandler(HTTPException)
def http_error(exc):
    return jsonify(error=exc.description), exc.code


@app.errorhandler(Exception)
def internal_error(exc):
    app.logger.error('API error: %s', type(exc).__name__)
    return jsonify(error='Interner Fehler. Add-on-Protokoll prüfen.'), 500


@app.get('/')
def index():
    return render_template('index.html', csrf=CSRF)


@app.get('/api/status')
def status():
    with LOCK:
        active = public_job(current) if current else None
        if active:
            active['output'] = ''.join(current['chunks'])[-128 * 1024:]
        version_file = Path('/opt-bot-version.txt')
        return jsonify(current=active, history=list(reversed(history)),
                       bot_version=version_file.read_text().strip() if version_file.exists() else 'Testumgebung')


@app.route('/api/config', methods=['GET', 'PUT'])
def config_file():
    with LOCK:
        path = WORK / 'config.yaml'
        if request.method == 'GET':
            return jsonify(content=path.read_text())
        idle_required()
        text = request.get_json().get('content')
        value = parse_mapping(text)
        if not isinstance(value.get('login'), dict):
            abort(400, 'Die login-Konfiguration fehlt.')
        backup(path)
        atomic_write(path, text)
        return jsonify(ok=True)


@app.route('/api/credentials', methods=['GET', 'PUT'])
def account():
    with LOCK:
        saved = credentials()
        if request.method == 'GET':
            return jsonify(username=saved.get('username', ''), password_set=bool(saved.get('password')))
        idle_required()
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        if not isinstance(username, str) or not username.strip() or len(username) > 320:
            abort(400, 'Gültigen Benutzernamen eingeben.')
        if not isinstance(password, str) or len(password) > 4096:
            abort(400, 'Ungültiges Passwort.')
        if not password:
            password = saved.get('password', '')
        atomic_write(WORK / '.credentials.json', json.dumps(dict(username=username.strip(), password=password)))
        return jsonify(ok=True)


@app.get('/api/files')
def list_files():
    result = []
    with LOCK:
        for folder in ['ads', 'downloaded-ads']:
            for p in sorted((WORK / folder).rglob('*')):
                if not p.is_file() or p.is_symlink() or p.suffix.lower() not in {'.yaml', '.yml', '.json', '.draft'}:
                    continue
                name = p.relative_to(WORK).as_posix()
                try:
                    editable_path(name)
                    content = p.read_text() if p.stat().st_size <= MAX_TEXT else ''
                    obj = yaml.safe_load(content) or {}
                    if not isinstance(obj, dict):
                        obj = {}
                    result.append(dict(path=name, title=str(obj.get('title', p.name)),
                                       ad_id=obj.get('id'), active=obj.get('active', True), price=obj.get('price')))
                except (OSError, ValueError, UnicodeError, yaml.YAMLError, HTTPException):
                    result.append(dict(path=name, title=p.name, error=True))
        return jsonify(files=result)


@app.route('/api/file', methods=['GET', 'PUT', 'DELETE'])
def file():
    with LOCK:
        data = request.get_json() if request.method != 'GET' else request.args
        path = editable_path(data.get('path'))
        if request.method == 'GET':
            if not path.is_file():
                abort(404, 'Datei nicht gefunden.')
            if path.stat().st_size > MAX_TEXT:
                abort(413, 'Datei zu groß für den Editor.')
            return jsonify(content=path.read_text(), path=str(path.relative_to(WORK)))
        idle_required()
        if request.method == 'DELETE':
            if data.get('confirm') is not True:
                abort(400, 'Lokales Löschen bestätigen.')
            if not path.is_file():
                abort(404, 'Datei nicht gefunden.')
            backup(path)
            path.unlink()
        else:
            text = data.get('content')
            value = parse_mapping(text)
            if path.suffix == '.json':
                try:
                    json.loads(text)
                except ValueError:
                    abort(400, 'Für .json-Dateien ist gültiges JSON erforderlich.')
            if not isinstance(value.get('title'), str) or not value['title'].strip():
                abort(400, 'Ein Anzeigentitel ist erforderlich.')
            path.parent.mkdir(parents=True, exist_ok=True)
            backup(path)
            atomic_write(path, text)
        return jsonify(ok=True)


@app.post('/api/images')
def images():
    with LOCK:
        idle_required()
        if (WORK / 'ads').is_symlink() or (WORK / 'ads/images').is_symlink():
            abort(400, 'Symbolische Links sind nicht erlaubt.')
        uploads = request.files.getlist('files')
        if not uploads:
            abort(400, 'Keine Bilddateien ausgewählt.')
        saved = []
        for upload in uploads:
            suffix = Path(upload.filename or '').suffix.lower()
            if suffix not in {'.jpg', '.jpeg', '.png', '.webp'}:
                abort(400, 'Unterstützte Formate: JPG, PNG, WEBP.')
            raw = upload.read()
            valid = ((suffix in {'.jpg', '.jpeg'} and raw.startswith(b'\xff\xd8\xff')) or
                     (suffix == '.png' and raw.startswith(b'\x89PNG\r\n\x1a\n')) or
                     (suffix == '.webp' and raw.startswith(b'RIFF') and raw[8:12] == b'WEBP'))
            if not valid:
                abort(400, 'Datei entspricht nicht dem angegebenen Bildformat.')
            name = uuid.uuid4().hex + suffix
            path = WORK / 'ads/images' / name
            with path.open('xb') as stream:
                stream.write(raw)
            saved.append('images/' + name)
        return jsonify(paths=saved)


@app.post('/api/jobs')
def start_job():
    global current
    with LOCK:
        idle_required()
        command, selector, args = validate_job(request.get_json())
        current = dict(id=uuid.uuid4().hex, command=command, selector=selector, state='running',
                       started=time.time(), ended=None, returncode=None, chunks=deque(maxlen=256),
                       process=None, pty=None, stop_requested=False)
        history.append(public_job(current))
        while len(history) > 50:
            old = history.pop(0)
            (STATE / (old['id'] + '.log')).unlink(missing_ok=True)
        persist_history()
        threading.Thread(target=run_job, args=(current, args), daemon=True).start()
        return jsonify(job=public_job(current)), 202


@app.post('/api/jobs/stop')
def stop_job():
    with LOCK:
        if current is None or current['state'] != 'running':
            abort(409, 'Kein laufender Auftrag.')
        current['stop_requested'] = True
        return jsonify(ok=True)


@app.post('/api/jobs/enter')
def job_enter():
    with LOCK:
        if current is None or current['state'] != 'running' or current['pty'] is None:
            abort(409, 'Kein interaktiver Auftrag bereit.')
        os.write(current['pty'], b'\n')
        return jsonify(ok=True)


@app.get('/api/log/<job_id>')
def log(job_id):
    if not re.fullmatch(r'[a-f0-9]{32}', job_id):
        abort(400, 'Ungültige Auftrags-ID.')
    path = STATE / (job_id + '.log')
    if not path.is_file():
        abort(404, 'Protokoll nicht gefunden.')
    return send_file(path, as_attachment=True, download_name=f'kleinanzeigen-{job_id}.log', mimetype='text/plain')


def shutdown(_sig=None, _frame=None):
    with LOCK:
        if current and current['state'] == 'running':
            current['stop_requested'] = True
    deadline = time.monotonic() + 8
    while current and current['state'] == 'running' and time.monotonic() < deadline:
        time.sleep(0.1)
    raise SystemExit(0)


initialize()
if __name__ == '__main__':
    from waitress import serve
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    serve(app, host='127.0.0.1', port=5000, threads=4)
