import asyncio
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from flask import Flask
import yaml

ROOT=Path(__file__).parent
storage=types.ModuleType('storage')
storage.atomic_write=lambda p,s:(p.parent.mkdir(parents=True,exist_ok=True),p.write_text(s))
storage.mapping=yaml.safe_load
sys.modules['storage']=storage
sys.path.insert(0,str(ROOT/'app'))
import sync_hotfix as hotfix
import account_bridge as bridge

class Tests(unittest.TestCase):
 def test_structured_prefixed_output(self):
  row=dict(ad_id='123',title='A',state='active',expires=None)
  self.assertEqual(hotfix.structured_online('[INFO] '+hotfix.MARKER+json.dumps([row])),[row])
 def test_partial_rejected(self):
  for text in ['ID: 123',hotfix.MARKER+'{}',hotfix.MARKER+'[{}]']:
   with self.assertRaises(ValueError):hotfix.structured_online(text)
 def test_duplicate_rejected(self):
  row=dict(ad_id='1',title='A',state='active')
  with self.assertRaises(ValueError):hotfix.structured_online(hotfix.MARKER+json.dumps([row,row]))
 def test_state_mapping(self):
  self.assertEqual(bridge.validate_ads([dict(id=1,title='A',state='paused')])[0]['state'],'reserved')
 def test_empty_is_valid(self):
  self.assertEqual(hotfix.structured_online(hotfix.MARKER+'[]'),[])
 def test_profile_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config.yaml';p.write_text('browser:\n  user_data_dir: ./existing-profile\n  arguments: [--headless, --no-sandbox]\n')
   e=types.SimpleNamespace(store=types.SimpleNamespace(work=Path(d)))
   temp=hotfix.runtime_config(e,None);cfg=yaml.safe_load(temp.read_text())
   self.assertEqual(cfg['browser']['user_data_dir'],'./existing-profile')
   self.assertFalse(cfg['browser']['suppress_unsupported_flag_warning'])
   self.assertNotIn('--headless',cfg['browser']['arguments'])
   self.assertIn('--window-size=1280,800',cfg['browser']['arguments'])
 def test_manual_login_verified(self):
  async def original(*a,**k):raise TimeoutError()
  async def state(*a,**k):return types.SimpleNamespace(is_logged_in=True)
  module=types.ModuleType('kleinanzeigen_bot');module.login_flow=types.SimpleNamespace(get_login_state=state)
  with patch.dict(sys.modules,{'kleinanzeigen_bot':module}),patch('builtins.input',return_value=''):
   asyncio.run(bridge.bounded_login(original,object(),username='x'))
 def test_manual_login_not_assumed(self):
  async def original(*a,**k):raise TimeoutError()
  async def state(*a,**k):return types.SimpleNamespace(is_logged_in=False)
  module=types.ModuleType('kleinanzeigen_bot');module.login_flow=types.SimpleNamespace(get_login_state=state)
  with patch.dict(sys.modules,{'kleinanzeigen_bot':module}),patch('builtins.input',return_value=''):
   with self.assertRaises(RuntimeError):asyncio.run(bridge.bounded_login(original,object(),username='x'))
 def test_installer_and_idempotence(self):
  with tempfile.TemporaryDirectory() as d:
   addon=Path(d)/'addon';(addon/'app').mkdir(parents=True)
   (addon/'app/server.py').write_text('engine = Engine(store, BIN)\napp = Flask(__name__)\nif __name__ == "__main__":\n    pass\n')
   (addon/'app/engine.py').write_text('class Engine: pass\n')
   (addon/'Dockerfile').write_text('FROM debian:trixie-slim\nARG BUILD_VERSION=0.2.3\n')
   (addon/'config.yaml').write_text('version: "0.2.3"\n')
   for _ in range(2):
    p=subprocess.run([sys.executable,str(ROOT/'apply_hotfix.py'),str(addon)],capture_output=True,text=True)
    self.assertEqual(p.returncode,0,p.stderr)
   text=(addon/'app/server.py').read_text()
   self.assertEqual(text.count('install_sync_hotfix(engine, app)'),1)
   self.assertIn('0.2.4',(addon/'Dockerfile').read_text())
 def test_legacy_server_refused_without_changes(self):
  with tempfile.TemporaryDirectory() as d:
   addon=Path(d)/'addon';(addon/'app').mkdir(parents=True)
   p=addon/'app/server.py';p.write_text('current = None\n')
   (addon/'app/engine.py').write_text('class Engine: pass\n')
   result=subprocess.run([sys.executable,str(ROOT/'apply_hotfix.py'),str(addon)],capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0)
   self.assertEqual(p.read_text(),'current = None\n')

 def test_snapshot_visible_despite_detail_failure(self):
  import threading
  with tempfile.TemporaryDirectory() as d:
   work=Path(d);(work/'config.yaml').write_text('browser: {}\n')
   row=dict(ad_id='1',title='Visible immediately',state='active',expires=None)
   class Fake:
    def __init__(self):
     self.store=types.SimpleNamespace(work=work,state=work/'state',files=lambda:[])
     self.binary='original';self.lock=threading.RLock();self.shutdown_event=threading.Event()
     self.db=dict(online=[],synced_at=None,sync_error='old');self.logs=[]
    def persist(self):pass
    def append(self,j,t):self.logs.append(t)
    def start(self,*a,**k):return {}
    def execute(self,j,c,**k):
     if c=='list':return hotfix.MARKER+json.dumps([row])
     assert self.db['online']==[row]
     raise RuntimeError('detail failed')
   fake=Fake();app=Flask('test');hotfix.install(fake,app)
   with self.assertRaises(RuntimeError):fake.sync({})
   self.assertEqual(fake.db['online'],[row])
   self.assertIsNotNone(fake.db['synced_at'])
   self.assertIn('Detailimporte fehlen',fake.db['sync_error'])
   self.assertEqual(fake.binary,'original')
   self.assertFalse(list(work.glob('.sync-runtime-*')))
 def test_ui_refresh_and_version(self):
  import threading
  with tempfile.TemporaryDirectory() as d:
   fake=types.SimpleNamespace(store=types.SimpleNamespace(work=Path(d),state=Path(d)),
    execute=lambda *a,**k:None,start=lambda *a,**k:None,lock=threading.RLock(),db={})
   app=Flask('ui')
   app.add_url_rule('/',view_func=lambda:'<html><body>Home Assistant · 0.2.0</body></html>')
   hotfix.install(fake,app)
   response=app.test_client().get('/')
   self.assertIn(b'0.2.4',response.data)
   self.assertIn(b'await loadAds()',response.data)
   self.assertIn(b'haLoginNotice',response.data)
if __name__=='__main__':unittest.main(verbosity=2)
