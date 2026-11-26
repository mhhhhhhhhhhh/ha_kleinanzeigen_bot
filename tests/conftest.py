# SPDX-License-Identifier: AGPL-3.0-or-later
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import uuid
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'kleinanzeigen_bot/app'))

@pytest.fixture
def api(tmp_path,monkeypatch):
    work,state = tmp_path/'work',tmp_path/'state'
    work.mkdir()
    source = (ROOT/'tests/fake_bot.py').read_text()
    binary = tmp_path/'fake-bot'
    binary.write_text('#!'+sys.executable+'\n'+source)
    binary.chmod(0o755)
    monkeypatch.setenv('BOT_WORKSPACE',str(work))
    monkeypatch.setenv('BOT_STATE',str(state))
    monkeypatch.setenv('BOT_BINARY',str(binary))
    monkeypatch.setenv('JOB_TIMEOUT_MINUTES','1')
    monkeypatch.setenv('SUPERVISOR_TOKEN','SUPERVISOR-SHOULD-NOT-LEAK')
    spec = importlib.util.spec_from_file_location('server_test_'+uuid.uuid4().hex,ROOT/'kleinanzeigen_bot/app/server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    control = dict(online=[dict(id=101,title='Test laptop',state='active',expires='2026-12-01T00:00:00Z')])
    (work/'.fake-control.json').write_text(json.dumps(control))
    module.store.work.joinpath('.credentials.json').write_text(json.dumps(dict(username='offline@example.invalid',password='offline-secret-123456789')))
    module.store.work.joinpath('.credentials.json').chmod(0o600)
    client = module.app.test_client()
    module.client=client
    module.headers={'X-CSRF-Token':module.CSRF}
    def send(path,data=None,method='POST'):
        return client.open(path,method=method,json=data or {},headers=module.headers)
    def wait_done():
        for _ in range(500):
            result=client.get('/api/status').json['current']
            if result and result['state']!='running':
                # state transition + durable history/log update share one lock at completion
                module.engine.thread.join(timeout=3)
                return client.get('/api/status').json['current']
            time.sleep(.01)
        raise AssertionError('Fake job did not terminate')
    def start(command,path=None,confirm=True):
        response=send('/api/jobs',dict(command=command,path=path,confirm=confirm))
        assert response.status_code==202,response.json
        return wait_done()
    def sync():
        j=start('sync');assert j['state']=='success',j
        return client.get('/api/ads').json['ads']
    def modify(**updates):
        p=work/'.fake-control.json';value=json.loads(p.read_text());value.update(updates);p.write_text(json.dumps(value))
    def calls():
        p=work/'.fake-calls.jsonl'
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
    module.send,module.wait_done,module.start,module.sync,module.modify,module.calls=send,wait_done,start,sync,modify,calls
    yield module
    module.engine.stop()
