# SPDX-License-Identifier: AGPL-3.0-or-later
"""Home Assistant ingress API. The CLI runs in a single persistent worker."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import threading
import time
import yaml
from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException
from engine import Engine, Busy, Failed
from storage import Store, Invalid, atomic_write, mapping, jsonable

WORK = Path(os.environ.get('BOT_WORKSPACE', '/data/workspace'))
STATE = Path(os.environ.get('BOT_STATE', '/data/state'))
BIN = os.environ.get('BOT_BINARY', '/usr/local/bin/kleinanzeigen-bot')
CSRF = secrets.token_urlsafe(32)
os.umask(0o077)
store = Store(WORK, STATE)
DEFAULT_CONFIG = '''login:
  username: "${KLEINANZEIGEN_BOT_USERNAME}"
  password: "${KLEINANZEIGEN_BOT_PASSWORD}"
ad_files:
  - "./ads/**/*.{yaml,yml,json}"
  - "./downloaded-ads/**/*.{yaml,yml,json}"
download:
  dir: ./downloaded-ads
  folder_name_template: "ad_{id}"
  ad_file_name_template: "ad_{id}"
  preserve_local_settings: true
browser:
  user_data_dir: ./browser-profile
  use_private_window: false
  binary_location: /usr/bin/chromium
  suppress_unsupported_flag_warning: false
  arguments:
    - --no-sandbox
    - --disable-dev-shm-usage
    - --window-size=1280,800
publishing:
  delete_old_ads: AFTER_PUBLISH
  delete_old_ads_by_title: false
update_check:
  enabled: false
'''
if not (store.work/'config.yaml').exists():
    atomic_write(store.work/'config.yaml', DEFAULT_CONFIG)
engine = Engine(store, BIN, int(os.environ.get('JOB_TIMEOUT_MINUTES', '30'))*60)
app = Flask(__name__, template_folder=str(Path(__file__).parent/'templates'))
app.config['MAX_CONTENT_LENGTH'] = 20*1024*1024

@app.before_request
def protect():
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        if not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), CSRF):
            abort(403, 'Sicherheitstoken fehlt. Oberfläche neu laden.')
        if request.path != '/api/images':
            if not request.is_json:
                abort(415, 'JSON erwartet.')
            if not isinstance(request.get_json(), dict):
                abort(400, 'Ein JSON-Objekt wird erwartet.')

@app.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.errorhandler(HTTPException)
def http_error(exc):
    return jsonify(error=exc.description), exc.code

@app.errorhandler(Invalid)
def invalid(exc):
    return jsonify(error=str(exc)), 400

@app.errorhandler(Busy)
@app.errorhandler(FileExistsError)
def conflict(exc):
    return jsonify(error=str(exc)), 409

@app.errorhandler(FileNotFoundError)
def missing(exc):
    return jsonify(error='Datei nicht gefunden.'), 404

@app.errorhandler(Exception)
def internal_error(exc):
    app.logger.error('API error: %s', type(exc).__name__)
    return jsonify(error='Interner Fehler. Add-on-Protokoll prüfen.'), 500

@app.get('/')
def index():
    ingress = request.headers.get('X-Ingress-Path', '').rstrip('/')+'/'
    if not ingress.startswith('/') or ingress.startswith('//'):
        ingress = '/'
    return render_template('index.html', csrf=CSRF, ingress=ingress)

@app.get('/api/status')
def status():
    return jsonify(engine.status())

@app.get('/api/ads')
def ads():
    return jsonify(engine.listings())

@app.route('/api/file', methods=['GET','PUT','DELETE'])
def file():
    with engine.lock:
        data = request.args if request.method == 'GET' else request.get_json()
        name = data.get('path')
        p = store.path(name)
        if request.method == 'GET':
            obj, text = store.read(name)
            pics = [x.relative_to(store.work).as_posix() for x in store.image_files(name, obj)]
            return jsonify(path=name, content=text, data=jsonable(obj), revision=store.revision(name), images=pics,
                           policy=engine.db['policies'].get(name, {}))
        engine.idle()
        if request.method == 'PUT':
            if 'data' in data:
                if not isinstance(data['data'], dict):
                    raise Invalid('data muss ein Objekt sein.')
                obj = data['data']
                text = json.dumps(obj, ensure_ascii=False, indent=2) if p.suffix == '.json' else yaml.safe_dump(obj, allow_unicode=True, sort_keys=False)
            else:
                text = data.get('content')
            store.save(name, text, data.get('revision'))
            return jsonify(ok=True, revision=store.revision(name))
        if data.get('confirm') is not True:
            raise Invalid('Lokales Löschen bestätigen.')
        if data.get('revision') != store.revision(name):
            raise FileExistsError('Anzeige wurde geändert. Neu laden.')
        store.backup(p)
        p.unlink()
        engine.db['policies'].pop(name, None)
        engine.persist()
        return jsonify(ok=True)

@app.post('/api/images')
def images():
    with engine.lock:
        engine.idle()
        paths = store.upload(request.form.get('path'), request.files.getlist('files'))
        return jsonify(paths=paths)

@app.get('/api/image')
def image():
    with engine.lock:
        p = store.path(request.args.get('path'), image=True)
        if not p.is_file():
            raise FileNotFoundError(p)
        return send_file(p)

@app.route('/api/config', methods=['GET','PUT'])
def config():
    with engine.lock:
        p = store.work/'config.yaml'
        if request.method == 'GET':
            text = p.read_text()
            return jsonify(content=text, revision=hashlib.sha256(p.read_bytes()).hexdigest())
        engine.idle()
        data = request.get_json()
        if data.get('revision') != hashlib.sha256(p.read_bytes()).hexdigest():
            raise FileExistsError('Konfiguration wurde geändert. Neu laden.')
        text = data.get('content')
        obj = mapping(text)
        if not isinstance(obj.get('login'), dict):
            raise Invalid('login-Konfiguration fehlt.')
        # The UI only manages these folders. Do not let downloads silently go elsewhere.
        if not isinstance(obj.get('download', {}),dict):
            raise Invalid('download muss ein Objekt sein.')
        if obj.get('download', {}).get('dir', './downloaded-ads') not in {'./downloaded-ads', 'downloaded-ads', str(store.work/'downloaded-ads')}:
            raise Invalid('download.dir muss ./downloaded-ads bleiben.')
        if not isinstance(obj.get('ad_files'), list):
            raise Invalid('ad_files muss eine Liste sein.')
        store.backup(p)
        atomic_write(p, text)
        return jsonify(ok=True, revision=hashlib.sha256(p.read_bytes()).hexdigest())

@app.route('/api/credentials', methods=['GET','PUT'])
def credentials():
    with engine.lock:
        saved, _ = engine.secrets()
        if request.method == 'GET':
            return jsonify(username=saved.get('username',''), password_set=bool(saved.get('password')))
        engine.idle()
        data = request.get_json()
        username, password = data.get('username'), data.get('password')
        if not isinstance(username,str) or not username.strip() or len(username)>320 or not isinstance(password,str) or len(password)>4096:
            raise Invalid('Ungültiger Benutzername / Passwort.')
        username = username.strip()
        # Changing accounts requires a new session, never keep the old password silently.
        if saved.get('username') and username != saved['username']:
            raise Invalid('Kontowechsel erfordert einen separaten Workspace; bestehende Sitzung wird nicht wiederverwendet.')
        atomic_write(store.work/'.credentials.json', json.dumps(dict(username=username, password=password or saved.get('password',''))))
        return jsonify(ok=True)

@app.route('/api/settings', methods=['GET','PUT'])
def settings():
    if request.method == 'GET':
        with engine.lock:
            return jsonify(engine.db['settings'])
    return jsonify(engine.set_settings(request.get_json()))

@app.put('/api/policy')
def policy():
    data = request.get_json()
    return jsonify(engine.set_policy(data.get('path'), data.get('enabled'), data.get('days'),
                                    data.get('confirm'), data.get('reset',False)))

@app.post('/api/jobs')
def jobs():
    data = request.get_json()
    cmd, name = data.get('command'), data.get('path')
    if not isinstance(cmd,str):
        raise Invalid('command muss eine Zeichenkette sein.')
    if cmd in {'auto_extend','auto_republish'}:
        raise Invalid('Interner Automatik-Auftrag.')
    if cmd in {'publish','update','extend','reserve','activate','delete','refresh'} and data.get('confirm') is not True:
        raise Invalid('Online-Änderung ausdrücklich bestätigen.')
    if name is not None and cmd in {'sync','login','status','diagnose','version','help'}:
        raise Invalid('Dieser Auftrag akzeptiert keinen Dateipfad.')
    if cmd == 'sync' and data.get('if_idle') is True:
        with engine.lock:
            if engine.current and engine.current['state'] == 'running':
                return jsonify(job=engine.public(engine.current)), 202
            if not engine.has_account() or (engine.db['synced_at'] and time.time()-engine.db['synced_at']<300):
                return jsonify(skipped=True)
    return jsonify(job=engine.start(cmd, name)), 202

@app.post('/api/jobs/stop')
def stop():
    with engine.lock:
        if not engine.current or engine.current['state'] != 'running':
            raise Busy('Kein laufender Auftrag.')
        engine.current['stop_requested'] = True
        return jsonify(ok=True)

@app.post('/api/jobs/enter')
def enter():
    with engine.lock:
        if not engine.current or engine.current['state'] != 'running' or engine.current['pty'] is None:
            raise Busy('Kein interaktiver Auftrag bereit.')
        os.write(engine.current['pty'], b'\n')
        return jsonify(ok=True)

@app.get('/api/log/<job_id>')
def log(job_id):
    if not re.fullmatch(r'[a-f0-9]{32}',job_id):
        raise Invalid('Ungültige Auftrags-ID.')
    p = store.state/(job_id+'.log')
    if not p.is_file():
        raise FileNotFoundError(job_id)
    return send_file(p, as_attachment=True, download_name='kleinanzeigen-'+job_id+'.log', mimetype='text/plain')

if __name__ == '__main__':
    from waitress import serve
    def shutdown(*_):
        engine.stop()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    engine.start_scheduler()
    serve(app, host='127.0.0.1', port=5000, threads=4)
