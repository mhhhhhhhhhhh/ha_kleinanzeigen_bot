# SPDX-License-Identifier: AGPL-3.0-or-later
"""One browser worker, strict account snapshots, and persistent opt-in scheduling."""
from __future__ import annotations
import codecs
from datetime import datetime, timedelta, timezone
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
import yaml
from storage import Store, Invalid, atomic_write, mapping, numeric_id

class Busy(RuntimeError):
    pass

class Failed(RuntimeError):
    pass

DEFAULT_SETTINGS = dict(auto_sync=True, sync_minutes=60, auto_extend=False, extend_hours=6)

def timestamp(value) -> float | None:
    if isinstance(value, datetime):
        d = value
    elif isinstance(value, str):
        try:
            d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None
    if d.tzinfo is None:
        # Upstream has historically saved local timestamps without an offset.
        from zoneinfo import ZoneInfo
        d = d.replace(tzinfo=ZoneInfo('Europe/Berlin'))
    return d.timestamp()

def parse_online(output: str) -> list[dict]:
    """Parse the upstream render_published_ads format with --lang=en.

    Never turn an unrecognized/partial output into an empty successful list.
    """
    plain = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', output).replace('\r', '')
    if 'No online ads found.' in plain and not re.search(r'^ID:', plain, re.M):
        return []
    starts = list(re.finditer(r'^ID:\s*([1-9][0-9]*)\s*$', plain, re.M))
    if not starts:
        raise Failed('Online-Liste nicht erkannt. Bot-Version/Protokoll prüfen.')
    result, seen = [], set()
    for i, start in enumerate(starts):
        end = starts[i+1].start() if i+1 < len(starts) else len(plain)
        block = plain[start.end():end]
        values = {}
        for key in ['title', 'status', 'expires']:
            m = re.search(r'^\s+'+key+r':\s*([^\n]*)$', block, re.M)
            if not m:
                raise Failed('Online-Liste ist unvollständig: '+key)
            values[key] = m[1].strip()
        ad_id = start[1]
        if ad_id in seen:
            raise Failed('Doppelte ID in der Online-Liste.')
        seen.add(ad_id)
        result.append(dict(ad_id=ad_id, title=values['title'], state=values['status'],
                           expires=None if values['expires'] == '-' else values['expires']))
    return result

class Engine:
    def __init__(self, store: Store, binary: str, timeout: float = 1800):
        self.store, self.binary, self.timeout = store, binary, timeout
        self.lock = threading.RLock()
        self.current = None
        self.thread = None
        self.shutdown_event = threading.Event()
        self.db_path = store.state/'engine.json'
        if self.db_path.exists():
            # Broken state must not silently enable jobs or lose safety journals.
            self.db = json.loads(self.db_path.read_text())
        else:
            self.db = dict(settings=dict(DEFAULT_SETTINGS), policies={}, online=[], synced_at=None,
                           sync_error=None, last_sync_attempt=0, last_extend_attempt=0, history=[])
        self.db['settings'] = dict(DEFAULT_SETTINGS, **self.db.get('settings', {}))
        for job in self.db['history']:
            if job['state'] == 'running':
                job.update(state='interrupted', ended=time.time(), error='Neustart während Auftrag')
        for policy in self.db['policies'].values():
            if policy.get('inflight'):
                policy.update(blocked=True, reason='Neustart während Veröffentlichung: Online-Ergebnis zuerst prüfen.')
        self.persist()

    def persist(self):
        atomic_write(self.db_path, json.dumps(self.db, ensure_ascii=False))

    def idle(self):
        if self.current and self.current['state'] == 'running':
            raise Busy('Ein Bot-Auftrag läuft. Bearbeitung ist währenddessen gesperrt.')

    def secrets(self) -> tuple[dict, list[str]]:
        p = self.store.work/'.credentials.json'
        saved = json.loads(p.read_text()) if p.exists() else {}
        cfg = mapping((self.store.work/'config.yaml').read_text())
        login = cfg.get('login', {})
        hidden = [saved.get('password', ''), saved.get('username', '')]
        hidden.extend(v for v in login.values() if isinstance(v, str) and not v.startswith('${'))
        return saved, [s for s in hidden if s]

    def has_account(self):
        saved, _ = self.secrets()
        cfg = mapping((self.store.work/'config.yaml').read_text()).get('login', {})
        return bool(saved.get('username') or os.environ.get('KLEINANZEIGEN_BOT_USERNAME') or (cfg.get('username') and not str(cfg['username']).startswith('${')))

    def redact(self, text, hidden):
        text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
        for s in sorted(hidden, key=len, reverse=True):
            text = text.replace(s, '[VERBORGEN]')
        return text

    def public(self, job):
        if job is None:
            return None
        result = {k: job.get(k) for k in ['id', 'command', 'path', 'state', 'started', 'ended', 'returncode', 'error', 'automatic']}
        return result

    def status(self):
        with self.lock:
            j = self.public(self.current)
            if j:
                j['output'] = self.current['output'][-131072:]
            return dict(current=j, history=list(reversed(self.db['history'])), synced_at=self.db['synced_at'],
                        sync_error=self.db['sync_error'], settings=self.db['settings'])

    def listings(self):
        with self.lock:
            files = self.store.files()
            by_id = {}
            for f in files:
                if f.get('ad_id'):
                    by_id.setdefault(f['ad_id'], []).append(f)
            rows, used = [], set()
            for online in self.db['online']:
                local = by_id.get(online['ad_id'], [])
                if local:
                    for f in local:
                        used.add(f['path'])
                        row = dict(f, online=True, state=online['state'], expires=online['expires'],
                                   duplicate=len(local)>1, online_title=online['title'])
                        row['policy'] = self.db['policies'].get(f['path'], {})
                        rows.append(row)
                else:
                    rows.append(dict(online, online=True, path=None, price=None,
                                     error='Details/Bilder noch nicht importiert', policy={}))
            for f in files:
                if f['path'] not in used:
                    rows.append(dict(f, online=False, state='local' if not f.get('ad_id') else 'not-in-snapshot',
                                     expires=None, policy=self.db['policies'].get(f['path'], {})))
            return dict(ads=rows, synced_at=self.db['synced_at'], sync_error=self.db['sync_error'])

    def scoped_config(self, name: str) -> Path:
        # Config remains in workspace root: portable profile and all relative settings stay stable.
        config = mapping((self.store.work/'config.yaml').read_text())
        config['ad_files'] = [str(self.store.path(n)) for n in (name if isinstance(name,list) else [name])]
        config.setdefault('publishing', {})['delete_old_ads'] = 'AFTER_PUBLISH'
        config['publishing']['delete_old_ads_by_title'] = False
        config.setdefault('update_check', {})['enabled'] = False
        path = self.store.work/('.job-config-'+uuid.uuid4().hex+'.yaml')
        atomic_write(path, yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
        return path

    def append(self, job, text):
        with self.lock:
            job['output'] = (job['output']+text)[-1024*1024:]

    def execute(self, job: dict, command: str, selector=None, config=None) -> str:
        saved, hidden = self.secrets()
        env = dict(os.environ)
        env.pop('SUPERVISOR_TOKEN', None)
        # Do not override credentials supplied externally with empty saved values.
        if saved.get('username'):
            env['KLEINANZEIGEN_BOT_USERNAME'] = saved['username']
        if saved.get('password'):
            env['KLEINANZEIGEN_BOT_PASSWORD'] = saved['password']
        hidden.extend([env.get('KLEINANZEIGEN_BOT_PASSWORD',''), env.get('KLEINANZEIGEN_BOT_USERNAME','')])
        hidden = [s for s in hidden if s]
        env.update(TERM='dumb', NO_COLOR='1')
        args = [self.binary, command, '--workspace-mode=portable', '--lang=en',
                '--config='+str(config or self.store.work/'config.yaml'),
                '--logfile='+str(self.store.work/'bot.log')]
        if selector is not None:
            args.append('--ads='+selector)
        if command == 'download':
            args.append('--preserve-local-settings')
        master, slave = pty.openpty()
        process = None
        captured, pending = '', ''
        overlap = max([len(s) for s in hidden]+[1])
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        try:
            if job['stop_requested'] or self.shutdown_event.is_set():
                raise Failed('Auftrag gestoppt.')
            process = subprocess.Popen(args, cwd=self.store.work, env=env, stdin=slave, stdout=slave,
                                       stderr=slave, start_new_session=True, close_fds=True)
            os.close(slave)
            slave = None
            with self.lock:
                job.update(process=process, pty=master)
            self.append(job, '\n▶ '+command+((' --ads='+selector) if selector else '')+'\n')
            deadline, termination = time.monotonic()+self.timeout, None
            while True:
                if (job['stop_requested'] or self.shutdown_event.is_set() or time.monotonic() >= deadline) and termination is None:
                    job['termination'] = 'stopped' if job['stop_requested'] or self.shutdown_event.is_set() else 'timeout'
                    self.kill(process, signal.SIGTERM)
                    termination = time.monotonic()
                if termination and time.monotonic()-termination > 3:
                    self.kill(process, signal.SIGKILL)
                ready, _, _ = select.select([master], [], [], .1)
                if ready:
                    try:
                        raw = os.read(master, 8192)
                    except OSError as exc:
                        if exc.errno == errno.EIO:
                            break
                        raise
                    if not raw:
                        break
                    text = decoder.decode(raw)
                    captured += text
                    if len(captured) > 8*1024*1024:
                        raise Failed('Bot-Ausgabe zu groß; unvollständige Ergebnisse werden verworfen.')
                    pending += text
                    if len(pending) > overlap*2:
                        cut = len(pending)-overlap
                        for secret in hidden:
                            start = pending.rfind(secret, 0, min(len(pending), cut+len(secret)))
                            if start >= 0 and start < cut < start+len(secret):
                                cut = start
                        self.append(job, self.redact(pending[:cut], hidden))
                        pending = pending[cut:]
                elif process.poll() is not None:
                    break
            pending += decoder.decode(b'', final=True)
            self.append(job, self.redact(pending, hidden))
            code = process.wait(timeout=5)
            job['returncode'] = code
            if job.get('termination'):
                raise Failed('Auftrag gestoppt oder Zeitlimit überschritten.')
            if code != 0:
                raise Failed(f'Bot-Befehl {command} fehlgeschlagen (Exit {code}). Protokoll prüfen.')
            if command == 'download' and re.search(r'\b[1-9][0-9]*\s+failed\b', captured):
                raise Failed('Bot meldet fehlgeschlagene Downloads trotz Exit 0.')
            return captured
        finally:
            if process is not None:
                self.kill(process, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.kill(process, signal.SIGKILL)
                    process.wait(timeout=3)
            with self.lock:
                job.update(process=None, pty=None)
            for fd in [master, slave]:
                if fd is not None:
                    os.close(fd)
            (self.store.work/'bot.log').unlink(missing_ok=True)

    @staticmethod
    def kill(process, sig):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass

    def sync(self, job):
        with self.lock:
            self.db['last_sync_attempt'] = time.time()
            self.persist()
        try:
            ads = parse_online(self.execute(job, 'list'))
            with self.lock:
                self.db.update(online=ads, synced_at=time.time(), sync_error=None)
                self.persist()
                existing = {f['ad_id'] for f in self.store.files() if f.get('ad_id')}
            missing = [a['ad_id'] for a in ads if a['ad_id'] not in existing]
            for i in range(0, len(missing), 25):
                self.execute(job, 'download', ','.join(missing[i:i+25]))
            existing = {f['ad_id'] for f in self.store.files() if f.get('ad_id')}
            if any(a['ad_id'] not in existing for a in ads):
                raise Failed('Online-Liste geladen; einige Anzeigen-Details fehlen nach dem Download.')
        except Exception as exc:
            with self.lock:
                self.db['sync_error'] = str(exc)
                self.persist()
            raise

    def refresh(self, job, name):
        """Explicitly replace local content from online, retaining schedule/counters.

        Download into a staging folder first. A failed download leaves the
        original ad and all its images untouched.
        """
        import shutil
        original, ad_id = self.require_owned(name)
        config = self.scoped_config(name)
        stage = self.store.work/('refresh-'+uuid.uuid4().hex)
        stage.mkdir()
        try:
            cfg = mapping(config.read_text())
            cfg.setdefault('download', {}).update(dir=str(stage), folder_name_template='ad_{id}', ad_file_name_template='ad_{id}')
            atomic_write(config, yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
            self.execute(job, 'download', ad_id, config=config)
            paths = list(stage.rglob('*.yaml')) + list(stage.rglob('*.json'))
            matches = []
            for p in paths:
                obj = mapping(p.read_text())
                if numeric_id(obj.get('id')) == ad_id:
                    matches.append((p,obj))
            if len(matches) != 1:
                raise Failed('Online-Download hat nicht genau eine passende Anzeige geliefert.')
            source, downloaded = matches[0]
            # A separate Store applies the same image/path safety rules to staging data.
            # Move its downloaded tree into the expected allowed root before resolving.
            staging_root = stage/'downloaded-ads'
            staging_root.mkdir()
            for child in list(stage.iterdir()):
                if child != staging_root:
                    shutil.move(str(child),str(staging_root/child.name))
            source = staging_root/source.relative_to(stage)
            staged_store = Store(stage,stage/'state')
            source_name = source.relative_to(stage).as_posix()
            pictures = staged_store.image_files(source_name,downloaded,strict=True)
            self.store.archive(name)
            target = self.store.path(name)
            image_dir = target.parent/'images'/('online-'+uuid.uuid4().hex)
            self.store.path((image_dir/'check.jpg').relative_to(self.store.work).as_posix(),image=True)
            image_dir.mkdir(parents=True)
            downloaded['images'] = []
            for i,picture in enumerate(pictures):
                destination = image_dir/(f'{i:03d}'+picture.suffix.lower())
                shutil.copyfile(picture,destination)
                destination.chmod(0o600)
                downloaded['images'].append(destination.relative_to(target.parent).as_posix())
            for key in ['auto_price_reduction','republication_interval','repost_count','price_reduction_count']:
                if key in original:
                    downloaded[key] = original[key]
            # Preserve confirmed publication timestamps for local schedules.
            for key in ['created_on','updated_on']:
                if key in original:
                    downloaded[key] = original[key]
            text = json.dumps(downloaded,ensure_ascii=False,indent=2) if target.suffix=='.json' else yaml.safe_dump(downloaded,allow_unicode=True,sort_keys=False)
            self.store.backup(target)
            atomic_write(target,text)
        finally:
            config.unlink(missing_ok=True)
            shutil.rmtree(stage,ignore_errors=True)

    def require_owned(self, name: str, active=False):
        obj, _ = self.store.read(name)
        ad_id = numeric_id(obj.get('id'))
        if not ad_id:
            raise Invalid('Diese Anzeige hat noch keine Online-ID.')
        if not self.db['synced_at'] or time.time()-self.db['synced_at'] > 7200:
            raise Invalid('Online-Stand ist nicht aktuell. Zuerst synchronisieren.')
        online = next((a for a in self.db['online'] if a['ad_id'] == ad_id), None)
        if not online:
            raise Invalid('Anzeige nicht im eigenen aktuellen Online-Konto gefunden.')
        matches = [f for f in self.store.files() if f.get('ad_id') == ad_id]
        if len(matches) != 1:
            raise Invalid('Doppelte lokale Anzeigen-ID. Duplikat zuerst entfernen.')
        if active and (online['state'] != 'active' or obj.get('active', True) is not True):
            raise Invalid('Nur aktive, nicht reservierte Anzeigen werden neu eingestellt.')
        return obj, ad_id

    def action(self, job, command: str, name: str):
        obj, _ = self.store.read(name)
        if command != 'verify':
            if command != 'publish' or numeric_id(obj.get('id')):
                self.require_owned(name, active=command == 'publish')
            if command in {'publish', 'update'} and obj.get('active', True) is not True:
                raise Invalid('Lokale Anzeige ist deaktiviert. active auf true setzen.')
            if self.store.path(name).suffix == '.draft':
                raise Invalid('Importierten Entwurf zuerst als vollständige .yaml-Anzeige speichern.')
        config = self.scoped_config(name)
        try:
            if command in {'publish', 'update'}:
                self.store.image_files(name, obj, strict=True)
                self.execute(job, 'verify', config=config)
                self.store.archive(name)
            selector = None if command == 'verify' else (numeric_id(obj.get('id')) or 'new')
            if command == 'publish':
                with self.lock:
                    policy = self.db['policies'].setdefault(name, dict(enabled=False, days=7))
                    if policy.get('blocked') and job['command'] != 'auto_republish':
                        raise Failed('Veröffentlichung gesperrt: Online-Ergebnis prüfen und Sperre aufheben.')
                    policy.update(inflight=True, blocked=True, reason='Veröffentlichung noch nicht bestätigt.')
                    self.persist()
            self.execute(job, command, selector=selector, config=config)
            if command == 'publish':
                with self.lock:
                    published, _ = self.store.read(name)
                    new_id = numeric_id(published.get('id'))
                    if not new_id or new_id == numeric_id(obj.get('id')):
                        raise Failed('Keine neue Anzeigen-ID bestätigt. Online-Ergebnis manuell prüfen.')
                    policy.update(inflight=False, blocked=False, reason=None,
                                  last_published=time.time(), last_id=new_id)
                    self.persist()
        finally:
            config.unlink(missing_ok=True)

    def republish(self, job, name):
        with self.lock:
            self.require_owned(name, active=True)
            policy = self.db['policies'][name]
            if policy.get('blocked'):
                raise Failed('Automatik für diese Anzeige ist gesperrt.')
            old_id = numeric_id(self.store.read(name)[0].get('id'))
            # Durable safety journal BEFORE the external write. Never blindly retry.
            policy.update(inflight=True, blocked=True, reason='Veröffentlichung läuft / Ergebnis noch nicht bestätigt.')
            self.persist()
        self.action(job, 'publish', name)
        with self.lock:
            obj, _ = self.store.read(name)
            new_id = numeric_id(obj.get('id'))
            if not new_id or new_id == old_id:
                raise Failed('Keine neue Anzeigen-ID bestätigt. Online-Ergebnis manuell prüfen.')
            policy.update(inflight=False, blocked=False, reason=None, last_published=time.time(), last_id=new_id)
            self.persist()

    def start(self, command: str, path=None, automatic=False):
        with self.lock:
            self.idle()
            if command not in {'sync', 'login', 'verify', 'status', 'diagnose', 'version', 'help',
                               'publish', 'update', 'extend', 'reserve', 'activate', 'delete', 'refresh', 'auto_extend', 'auto_republish'}:
                raise Invalid('Unbekannter Auftrag.')
            if command in {'publish','update','extend','reserve','activate','delete','refresh','auto_republish'}:
                if not path:
                    raise Invalid('Eine einzelne Anzeigen-Datei muss ausgewählt werden.')
                self.store.read(path)
            job = dict(id=uuid.uuid4().hex, command=command, path=path, automatic=automatic,
                       state='running', started=time.time(), ended=None, returncode=None, error=None,
                       output='', process=None, pty=None, stop_requested=False)
            self.current = job
            if command == 'auto_republish':
                self.db['policies'][path]['last_attempt'] = time.time()
            self.db['history'].append(self.public(job))
            for old in self.db['history'][:-50]:
                (self.store.state/(old['id']+'.log')).unlink(missing_ok=True)
            self.db['history'] = self.db['history'][-50:]
            self.persist()
            self.thread = threading.Thread(target=self.run, args=(job,), daemon=True)
            self.thread.start()
            return self.public(job)

    def run(self, job):
        try:
            command, name = job['command'], job['path']
            if command == 'sync':
                self.sync(job)
            elif command == 'auto_extend':
                self.sync(job)
                with self.lock:
                    self.db['last_extend_attempt'] = time.time()
                    self.persist()
                # Explicit IDs extend even when local active:false. Reserved ads stay untouched.
                online_ids = {a['ad_id'] for a in self.db['online'] if a['state'] == 'active'
                              and (timestamp(a.get('expires')) is None or
                                   time.time() < timestamp(a['expires']) <= time.time()+8*86400)}
                candidates = [f for f in self.store.files() if f.get('ad_id') in online_ids and not f.get('error')]
                for f in candidates:
                    self.require_owned(f['path'])
                if candidates:
                    config = self.scoped_config([f['path'] for f in candidates])
                    try:
                        self.execute(job, 'extend', ','.join(f['ad_id'] for f in candidates), config=config)
                    finally:
                        config.unlink(missing_ok=True)
                self.sync(job)
            elif command == 'auto_republish':
                self.sync(job)
                self.republish(job, name)
                self.sync(job)
            elif command == 'refresh':
                self.refresh(job,name)
            elif name:
                self.action(job, command, name)
                if command in {'publish','update','extend','reserve','activate','delete'}:
                    # Remember manual successful republishing, too.
                    if command == 'publish' and name in self.db['policies']:
                        with self.lock:
                            policy = self.db['policies'][name]
                            policy['last_published'] = time.time()
                            self.persist()
                    self.sync(job)
            else:
                self.execute(job, command)
            job['state'] = 'success'
        except Exception as exc:
            job.update(state=job.get('termination', 'failed'), error=str(exc) if isinstance(exc, (Invalid, Failed, Busy, FileNotFoundError)) else type(exc).__name__)
            self.append(job, '\nFEHLER: '+job['error']+'\n')
        finally:
            with self.lock:
                job['ended'] = time.time()
                self.db['history'] = [h for h in self.db['history'] if h['id'] != job['id']]+[self.public(job)]
                atomic_write(self.store.state/(job['id']+'.log'), job['output'])
                self.persist()

    def set_policy(self, name, enabled, days, confirmed=False, reset=False):
        with self.lock:
            self.idle()
            if type(reset) is not bool:
                raise Invalid('reset muss bool sein.')
            if type(enabled) is not bool or type(days) is not int or not 1 <= days <= 365:
                raise Invalid('Intervall: ganze Zahl von 1 bis 365 Tagen; enabled: bool.')
            if (enabled or reset) and confirmed is not True:
                raise Invalid('Automatisches Neueinstellen muss ausdrücklich bestätigt werden.')
            obj, _ = self.store.read(name)
            old = self.db['policies'].get(name, {})
            if enabled:
                self.require_owned(name, active=True)
                self.store.image_files(name, obj, strict=True)
            policy = dict(old, enabled=enabled, days=days)
            policy.setdefault('last_published', timestamp(obj.get('updated_on')) or timestamp(obj.get('created_on')) or time.time())
            if reset:
                policy.update(blocked=False, inflight=False, reason=None)
                # Explicit recovery grants a fresh full interval, not an immediate duplicate.
                policy['last_published'] = time.time()
            self.db['policies'][name] = policy
            self.persist()
            return policy

    def set_settings(self, data):
        with self.lock:
            self.idle()
            result = dict(self.db['settings'])
            for key in ['auto_sync', 'auto_extend']:
                if key in data:
                    if type(data[key]) is not bool:
                        raise Invalid(key+' muss bool sein.')
                    result[key] = data[key]
            for key, low, high in [('sync_minutes', 10, 1440), ('extend_hours', 1, 48)]:
                if key in data:
                    if type(data[key]) is not int or not low <= data[key] <= high:
                        raise Invalid(f'{key}: {low} bis {high}.')
                    result[key] = data[key]
            if result['auto_extend'] and data.get('confirm') is not True:
                raise Invalid('Automatische Konto-Verlängerung bestätigen.')
            self.db['settings'] = result
            self.persist()
            return result

    def tick(self, now=None):
        now = time.time() if now is None else now
        with self.lock:
            if self.shutdown_event.is_set() or (self.current and self.current['state'] == 'running') or not self.has_account():
                return None
            cfg = self.db['settings']
            if cfg['auto_extend'] and now-self.db['last_extend_attempt'] >= cfg['extend_hours']*3600:
                # Attempt timestamp is persistent even if login fails before extending.
                self.db['last_extend_attempt'] = now
                self.persist()
                return self.start('auto_extend', automatic=True)
            if cfg['auto_sync'] and now-self.db['last_sync_attempt'] >= cfg['sync_minutes']*60:
                return self.start('sync', automatic=True)
            # Prevent tight retries after a read/login failure before a republish journal.
            if self.current and self.current['automatic'] and self.current['state'] != 'success' and now-(self.current['ended'] or now) < 3600:
                return None
            if not self.db['synced_at'] or now-self.db['synced_at'] > 7200:
                due_policy = any(p.get('enabled') and not p.get('blocked') and not p.get('inflight')
                                 and now-p.get('last_published',now) >= p['days']*86400
                                 for p in self.db['policies'].values())
                if due_policy and now-self.db['last_sync_attempt'] >= 3600:
                    return self.start('sync',automatic=True)
                return None
            owned = {a['ad_id'] for a in self.db['online'] if a['state'] == 'active'}
            for name, policy in sorted(self.db['policies'].items()):
                if not policy.get('enabled') or policy.get('blocked') or policy.get('inflight'):
                    continue
                if now-policy.get('last_attempt', 0) < 3600:
                    continue
                if now-policy['last_published'] < policy['days']*86400:
                    continue
                try:
                    obj, _ = self.store.read(name)
                    if numeric_id(obj.get('id')) not in owned or obj.get('active', True) is not True:
                        continue
                    self.require_owned(name, active=True)
                except (Invalid, OSError):
                    continue
                return self.start('auto_republish', name, automatic=True)
            return None

    def scheduler(self):
        while not self.shutdown_event.wait(30):
            try:
                self.tick()
            except Exception:
                # Do not die silently; detailed job errors remain in the GUI.
                import logging
                logging.exception('Scheduler tick failed')

    def start_scheduler(self):
        self.scheduler_thread = threading.Thread(target=self.scheduler, daemon=True)
        self.scheduler_thread.start()

    def stop(self):
        self.shutdown_event.set()
        with self.lock:
            if self.current and self.current['state'] == 'running':
                self.current['stop_requested'] = True
        if self.thread:
            self.thread.join(timeout=10)
