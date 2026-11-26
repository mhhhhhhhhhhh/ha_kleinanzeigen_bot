# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import datetime, timezone
import json
import time
from unittest.mock import patch
import pytest
from engine import Engine, Failed, parse_online, timestamp
from storage import Invalid, Store, atomic_write


def enable(api,name,days=7):
    r=api.send('/api/policy',{'path':name,'enabled':True,'days':days,'confirm':True},'PUT')
    assert r.status_code==200,r.json
    return r.json


def test_automation_off_by_default(api):
    assert api.engine.db['settings']['auto_extend'] is False
    assert api.engine.db['policies']=={}

@pytest.mark.parametrize('days',[0,-1,366,1.5,True,'7',None])
def test_interval_validated(api,days):
    name=api.sync()[0]['path']
    assert api.send('/api/policy',{'path':name,'enabled':True,'days':days,'confirm':True},'PUT').status_code==400

def test_policy_confirmation_required(api):
    name=api.sync()[0]['path']
    assert api.send('/api/policy',{'path':name,'enabled':True,'days':7},'PUT').status_code==400

def test_settings_validation(api):
    assert api.send('/api/settings',{'auto_extend':True},'PUT').status_code==400
    assert api.send('/api/settings',{'auto_extend':True,'confirm':True},'PUT').status_code==200
    assert api.send('/api/settings',{'sync_minutes':1},'PUT').status_code==400
    assert api.send('/api/settings',{'auto_sync':'false'},'PUT').status_code==400

def test_policy_persisted_across_restart(api):
    name=api.sync()[0]['path'];policy=enable(api,name,11)
    restarted=Engine(api.store,api.BIN)
    assert restarted.db['policies'][name]==policy
    assert restarted.db['online']==api.engine.db['online']

def test_scheduler_due_and_new_id(api):
    name=api.sync()[0]['path'];enable(api,name,7)
    api.engine.db['policies'][name]['last_published']=time.time()-7*86400-1
    job=api.engine.tick()
    assert job['command']=='auto_republish'
    done=api.wait_done();assert done['state']=='success',done
    obj,_=api.store.read(name)
    assert obj['id']!=101
    policy=api.engine.db['policies'][name]
    assert not policy['blocked'] and not policy['inflight']
    assert policy['last_id']==str(obj['id'])
    assert api.engine.tick() is None

def test_scheduler_exact_x_days(api):
    name=api.sync()[0]['path'];enable(api,name,3)
    now=time.time();api.engine.db['policies'][name]['last_published']=now-3*86400
    with patch.object(api.engine,'start',return_value={'scheduled':True}) as start:
        assert api.engine.tick(now-.01) is None
        assert api.engine.tick(now)=={'scheduled':True}
        start.assert_called_once_with('auto_republish',name,automatic=True)

def test_uncertain_publish_blocked_no_retry(api):
    name=api.sync()[0]['path'];enable(api,name)
    api.modify(uncertain_publish=True)
    job=api.engine.start('auto_republish',name,automatic=True)
    done=api.wait_done();assert done['state']=='failed'
    policy=api.engine.db['policies'][name]
    assert policy['blocked'] and policy['inflight']
    restarted=Engine(api.store,api.BIN)
    assert restarted.db['policies'][name]['blocked']
    api.engine.db['last_sync_attempt']=time.time()
    assert api.engine.tick(time.time()+3601) is None or api.engine.current['command']=='sync'
    assert len([c for c in api.calls() if c['command']=='publish'])==1

def test_reset_requires_confirmation_and_fresh_interval(api):
    name=api.sync()[0]['path'];enable(api,name)
    api.engine.db['policies'][name].update(blocked=True,inflight=True)
    assert api.send('/api/policy',{'path':name,'enabled':True,'days':7,'reset':True},'PUT').status_code==400
    r=api.send('/api/policy',{'path':name,'enabled':True,'days':7,'reset':True,'confirm':True},'PUT')
    assert r.status_code==200
    assert not r.json['blocked'] and not r.json['inflight']
    assert time.time()-r.json['last_published']<1

def test_reserved_missing_disabled_no_automatic_publish(api):
    name=api.sync()[0]['path'];enable(api,name)
    api.engine.db['policies'][name]['last_published']=time.time()-99*86400
    for state in ['reserved','inactive']:
        api.engine.db['online'][0]['state']=state
        assert api.engine.tick() is None
    api.engine.db['online']=[]
    assert api.engine.tick() is None

def test_busy_tick_does_not_start_second_browser(api):
    api.send('/api/jobs',{'command':'login'})
    assert api.engine.tick() is None
    api.engine.current['stop_requested']=True
    api.wait_done()

def test_automatic_extend_imports_and_preserves_id(api):
    api.engine.db['settings']['auto_extend']=True
    from datetime import timedelta
    api.modify(online=[dict(id=101,title='Test laptop',state='active',expires=(datetime.now(timezone.utc)+timedelta(days=3)).isoformat())])
    job=api.engine.tick();assert job['command']=='auto_extend'
    done=api.wait_done();assert done['state']=='success',done
    assert api.store.files()[0]['ad_id']=='101'
    assert api.engine.db['online'][0]['expires']=='2027-02-01T00:00:00Z'
    assert not any(c['command']=='publish' for c in api.calls())
    assert any(c['command']=='extend' and c['args']['--ads']=='101' for c in api.calls())

def test_automatic_extend_failure_backoff(api):
    api.engine.db['settings']['auto_extend']=True
    api.modify(fail_list=True)
    api.engine.tick();assert api.wait_done()['state']=='failed'
    assert api.engine.db['last_extend_attempt']>0
    with patch.object(api.engine,'start') as start:
        api.engine.tick()
        assert not any(c.args[0]=='auto_extend' for c in start.call_args_list)

def test_parser_preserves_unknown_status(api):
    rows=parse_online('Banner\nID: 123\n  title: A : B\n  status: review\n  expires: -\nDONE')
    assert rows[0]['state']=='review' and rows[0]['expires'] is None
    assert rows[0]['title']=='A : B'

@pytest.mark.parametrize('output',['DONE','ID: 123\n  title: Partial','ID: 1\n  title: A\n  status: active\n  expires: -\nID: 1\n  title: B\n  status: active\n  expires: -'])
def test_parser_rejects_partial_or_duplicate(output):
    with pytest.raises(Failed):
        parse_online(output)

def test_timestamp_berlin_for_legacy_naive_dates():
    assert timestamp('2026-01-01T00:00:00')==timestamp('2025-12-31T23:00:00Z')
    assert timestamp('bad') is None


def test_manual_uncertain_publish_also_blocked(api):
    name=api.sync()[0]['path'];enable(api,name)
    api.modify(uncertain_publish=True)
    assert api.start('publish',name)['state']=='failed'
    policy=api.engine.db['policies'][name]
    assert policy['blocked'] and policy['inflight']
    api.modify(uncertain_publish=False)
    assert api.start('publish',name)['state']=='failed'
    assert len([c for c in api.calls() if c['command']=='publish'])==1


def test_success_exit_without_new_id_is_not_success(api):
    name=api.sync()[0]['path'];api.modify(same_id=True)
    j=api.start('publish',name)
    assert j['state']=='failed'
    assert api.engine.db['policies'][name]['blocked']


def test_scheduler_backoff_survives_restart(api):
    name=api.sync()[0]['path'];enable(api,name)
    policy=api.engine.db['policies'][name]
    policy.update(last_published=time.time()-99*86400,last_attempt=time.time())
    api.engine.persist()
    restarted=Engine(api.store,api.BIN)
    with patch.object(restarted,'start') as start:
        assert restarted.tick() is None
        start.assert_not_called()


def test_extend_skips_far_future_and_reserved(api):
    from datetime import timedelta
    near=(datetime.now(timezone.utc)+timedelta(days=3)).isoformat()
    far=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()
    api.modify(online=[dict(id=101,title='Near',state='active',expires=near),
                       dict(id=102,title='Far',state='active',expires=far),
                       dict(id=103,title='Reserved',state='reserved',expires=near),
                       dict(id=104,title='Near too',state='active',expires=near)])
    api.engine.db['settings']['auto_extend']=True
    api.engine.tick();assert api.wait_done()['state']=='success'
    calls=[c for c in api.calls() if c['command']=='extend']
    assert len(calls)==1
    assert set(calls[0]['args']['--ads'].split(','))=={'101','104'}


def test_corrupt_state_fails_closed(api):
    api.engine.db_path.write_text('{invalid')
    with pytest.raises(json.JSONDecodeError):
        Engine(api.store,api.BIN)


def test_environment_account_can_trigger_sync(api,monkeypatch):
    (api.store.work/'.credentials.json').unlink()
    monkeypatch.setenv('KLEINANZEIGEN_BOT_USERNAME','env@example.invalid')
    monkeypatch.setenv('KLEINANZEIGEN_BOT_PASSWORD','env-secret')
    assert api.engine.has_account()
    job=api.engine.tick()
    assert job['command']=='sync'
    assert api.wait_done()['state']=='success'


def test_reset_type_rejected(api):
    name=api.sync()[0]['path']
    r=api.send('/api/policy',{'path':name,'enabled':True,'days':7,'confirm':True,'reset':'yes'},'PUT')
    assert r.status_code==400


def test_due_policy_requests_fresh_snapshot_even_without_periodic_sync(api):
    name=api.sync()[0]['path'];enable(api,name)
    api.engine.db['settings']['auto_sync']=False
    api.engine.db['policies'][name]['last_published']=time.time()-99*86400
    api.engine.db['synced_at']=time.time()-9000
    api.engine.db['last_sync_attempt']=time.time()-9000
    with patch.object(api.engine,'start',return_value={'scheduled':'sync'}) as start:
        assert api.engine.tick()=={'scheduled':'sync'}
        start.assert_called_once_with('sync',automatic=True)
