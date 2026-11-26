# SPDX-License-Identifier: AGPL-3.0-or-later
"""Targeted compatibility patch for the 0.2.x Engine used by server.py."""
import json
import os
from pathlib import Path
import re
import sys
import shlex
import time
import yaml
from storage import atomic_write, mapping

MARKER='HA_ACCOUNT_ADS_V1='

def structured_online(text):
    plain=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',text).replace('\r','')
    payloads=[]
    for line in plain.splitlines():
        pos=line.find(MARKER)
        if pos>=0:
            payloads.append(line[pos+len(MARKER):])
    if len(payloads)!=1:
        raise ValueError('Keine eindeutige strukturierte Online-Liste vom Original-Bot erhalten.')
    result=json.loads(payloads[0])
    if not isinstance(result,list):
        raise ValueError('Ungültige strukturierte Online-Liste.')
    seen=set()
    for row in result:
        if not isinstance(row,dict) or not re.fullmatch(r'[1-9][0-9]*',str(row.get('ad_id',''))):
            raise ValueError('Ungültige Online-Anzeigen-ID.')
        if row['ad_id'] in seen or not isinstance(row.get('state'),str) or not isinstance(row.get('title'),str):
            raise ValueError('Ungültige oder doppelte Online-Anzeige.')
        seen.add(row['ad_id'])
    return result


def runtime_config(engine,config):
    p=Path(config or engine.store.work/'config.yaml')
    cfg=mapping(p.read_text())
    browser=cfg.setdefault('browser',{})
    browser['use_private_window']=False
    browser['suppress_unsupported_flag_warning']=False
    # Keep the profile path: existing authentication must not be discarded.
    args=browser.get('arguments',[]) or []
    if not isinstance(args,list):
        raise ValueError('browser.arguments muss eine Liste sein.')
    args=[a for a in args if isinstance(a,str) and not a.startswith(('--headless','--incognito','--guest','--window-size'))]
    for option in ['--no-sandbox','--disable-dev-shm-usage','--window-size=1280,800']:
        if option not in args:args.append(option)
    browser['arguments']=args
    cfg.setdefault('update_check',{})['enabled']=False
    # Don't introduce an additional indefinite diagnostic pause.
    cfg.setdefault('diagnostics',{})['pause_on_login_detection_failure']=False
    path=p.with_name('.sync-runtime-'+os.urandom(12).hex()+'.yaml')
    atomic_write(path,yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False))
    return path


def install(engine,app):
    if getattr(engine,'_sync_hotfix_installed',False):return
    engine._sync_hotfix_installed=True
    original_execute=engine.execute
    bridge=Path(__file__).with_name('account_bridge.py')
    launcher=engine.store.state/'account-bridge'
    # CLI interpreter includes the installed upstream package.
    python='/opt/venv/bin/python' if Path('/opt/venv/bin/python').exists() else sys.executable
    atomic_write(launcher,'#!/bin/sh\nexec '+shlex.quote(python)+' '+shlex.quote(str(bridge))+' "$@"\n')
    launcher.chmod(0o700)

    def execute(job,command,selector=None,config=None):
        runtime=None
        previous=engine.binary
        try:
            if command in {'list','download','login'}:
                runtime=runtime_config(engine,config)
                engine.binary=str(launcher)
            return original_execute(job,command,selector=selector,config=runtime or config)
        finally:
            engine.binary=previous
            if runtime:runtime.unlink(missing_ok=True)
    engine.execute=execute

    def sync(job):
        with engine.lock:
            engine.db['last_sync_attempt']=time.time()
            engine.db['sync_error']=None
            engine.persist()
        try:
            online=structured_online(engine.execute(job,'list'))
            with engine.lock:
                engine.db.update(online=online,synced_at=time.time(),sync_error=None)
                engine.persist()
            engine.append(job,f'\n[HA_SYNC] {len(online)} Online-Anzeigen geladen; Details werden importiert.\n')
            existing={str(f['ad_id']) for f in engine.store.files() if f.get('ad_id')}
            missing=[a['ad_id'] for a in online if a['ad_id'] not in existing]
            errors=[]
            for i in range(0,len(missing),25):
                if job.get('stop_requested') or engine.shutdown_event.is_set():
                    raise RuntimeError('Abgleich gestoppt; bereits geladene Anzeigen bleiben sichtbar.')
                try:
                    engine.execute(job,'download',','.join(missing[i:i+25]))
                except Exception as exc:
                    errors.append(str(exc))
                    break
            existing={str(f['ad_id']) for f in engine.store.files() if f.get('ad_id')}
            remaining=[a['ad_id'] for a in online if a['ad_id'] not in existing]
            if remaining or errors:
                raise RuntimeError(f'{len(online)} Anzeigen sichtbar, {len(remaining)} Detailimporte fehlen. '+ '; '.join(errors))
        except Exception as exc:
            with engine.lock:
                engine.db['sync_error']=str(exc)
                engine.persist()
            raise
    engine.sync=sync

    original_start=engine.start
    def start(command,*args,**kwargs):
        result=original_start(command,*args,**kwargs)
        if command in {'sync','login'}:
            with engine.lock:
                engine.db['sync_error']=None
                engine.persist()
        return result
    engine.start=start

    # UI-only observer: snapshot and imported files refresh WHILE jobs run.
    @app.after_request
    def hotfix_ui(response):
        if response.mimetype!='text/html':return response
        response.direct_passthrough=False
        text=response.get_data(as_text=True)
        script="""<script>
(function(){
 let pending=false;
 setInterval(async function(){
  if(pending)return;pending=true;
  try{
   if(typeof loadAds==='function')await loadAds();
   if(typeof api==='function'){
    const data=await api('api/status');const job=data.current;
    const output=job&&job.output||'';
    const note=document.getElementById('haLoginNotice');
    if(note){note.hidden=!(job&&job.state==='running'&&output.includes('[HA_LOGIN_REQUIRED]')&&!output.includes('[HA_LOGIN_CONFIRMED]'));}
   }
  }catch(e){}finally{pending=false;}
 },2500);
 const section=document.getElementById('ads');
 if(section){const note=document.createElement('div');note.id='haLoginNotice';note.className='notice';note.hidden=true;
  note.textContent='Anmeldung erforderlich: Browserdesktop öffnen, anmelden und ENTER senden. Danach wird die Anzeigenliste geladen.';
  section.prepend(note);}
})();
</script>"""
        text=re.sub(r'Home Assistant · 0\.2\.\d+', 'Home Assistant · 0.2.4',text)
        response.set_data(text.replace('</body>',script+'</body>'))
        return response
