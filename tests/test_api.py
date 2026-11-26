# SPDX-License-Identifier: AGPL-3.0-or-later
from io import BytesIO
import json
from pathlib import Path
import time
import pytest
import re
from PIL import Image
from bs4 import BeautifulSoup


def test_homepage_and_ingress(api):
    r=api.client.get('/',headers={'X-Ingress-Path':'/api/hassio_ingress/test-token'})
    assert r.status_code==200
    assert b'{{ csrf' not in r.data
    assert b'/api/hassio_ingress/test-token/' in r.data
    soup=BeautifulSoup(r.data,'html.parser')
    assert soup.select_one('#ads:not([hidden])')
    assert soup.select_one('dialog#editor')
    assert not soup.select('script[src],link[rel="stylesheet"]')

@pytest.mark.parametrize('path',['/api/jobs','/api/settings','/api/policy','/api/file','/api/credentials','/api/config'])
def test_csrf(api,path):
    assert api.client.post(path,json={}).status_code in {403,405}
    method='POST' if path=='/api/jobs' else 'PUT'
    assert api.client.open(path,method=method,json={}).status_code==403

@pytest.mark.parametrize('value',[[],1,'text',None])
def test_json_object(api,value):
    assert api.client.post('/api/jobs',json=value,headers=api.headers).status_code in {400,415}

@pytest.mark.parametrize('name',['/etc/passwd','ads/../../config.yaml','ads/.secret.yaml','ads/ad_bad.txt','config.yaml','ads\\x.yaml'])
def test_path_traversal(api,name):
    assert api.client.get('/api/file',query_string={'path':name}).status_code==400

def test_symlink_blocked(api):
    p=api.store.work/'ads/link.yaml';p.symlink_to(api.store.work/'config.yaml')
    assert api.client.get('/api/file?path=ads/link.yaml').status_code==400

def test_credentials_not_returned(api):
    r=api.client.get('/api/credentials')
    assert r.json['password_set']
    assert 'password' not in r.json
    assert (api.store.work/'.credentials.json').stat().st_mode&0o777==0o600

def test_password_preserved(api):
    assert api.send('/api/credentials',{'username':'offline@example.invalid','password':''},'PUT').status_code==200
    assert api.engine.secrets()[0]['password']=='offline-secret-123456789'

def test_account_change_rejected(api):
    assert api.send('/api/credentials',{'username':'other@example.invalid','password':'new'},'PUT').status_code==400

def test_crud_revision_and_backup(api):
    name='ads/new.yaml'
    r=api.send('/api/file',{'path':name,'content':'title: New\ndescription: Hi\ncategory: 161/278\nactive: false\n'},'PUT')
    assert r.status_code==200,r.json
    original=api.client.get('/api/file?path='+name).json
    assert api.send('/api/file',{'path':name,'content':'title: Changed\n'},'PUT').status_code==409
    r=api.send('/api/file',{'path':name,'content':'title: Changed\n','revision':original['revision']},'PUT')
    assert r.status_code==200
    assert list((api.store.state/'backups').rglob('*.bak'))
    assert api.send('/api/file',{'path':name,'confirm':True,'revision':r.json['revision']},'DELETE').status_code==200
    assert api.client.get('/api/file?path='+name).status_code==404

@pytest.mark.parametrize('content',['[]','title: [','description: missing title'])
def test_invalid_yaml(api,content):
    assert api.send('/api/file',{'path':'ads/bad.yaml','content':content},'PUT').status_code==400

def test_json_extension_requires_json(api):
    assert api.send('/api/file',{'path':'ads/bad.json','content':'title: Bad'},'PUT').status_code==400

def test_managed_fields_protected(api):
    name=api.sync()[0]['path'];obj=api.client.get('/api/file?path='+name).json
    obj['data']['id']=222
    assert api.send('/api/file',{'path':name,'data':obj['data'],'revision':obj['revision']},'PUT').status_code==400

@pytest.mark.parametrize('cmd',['publish','update','extend','reserve','activate','delete'])
def test_external_write_confirmation(api,cmd):
    assert api.send('/api/jobs',{'command':cmd,'path':'ads/test.yaml'}).status_code==400

@pytest.mark.parametrize('data',[{'command':'sh'},{'command':'sync; rm -rf /'},{'command':'auto_republish'},{'command':'auto_extend'}])
def test_command_injection(api,data):
    assert api.send('/api/jobs',data).status_code==400

def test_sync_imports_data_and_images(api):
    rows=api.sync()
    assert len(rows)==1 and rows[0]['ad_id']=='101' and rows[0]['online']
    assert rows[0]['thumbnail'].endswith('.png')
    d=api.client.get('/api/file?path='+rows[0]['path']).json
    assert d['data']['special_attributes']=={'condition_s':'like_new'}
    assert d['data']['contact']['zipcode']=='01234'
    r=api.client.get('/api/image',query_string={'path':rows[0]['thumbnail']})
    assert r.status_code==200
    r.close()

def test_sync_all_not_first_page(api):
    api.modify(online=[dict(id=i,title='Listing '+str(i),state='active',expires='-') for i in range(100,137)])
    rows=api.sync()
    assert len(rows)==37
    assert len([c for c in api.calls() if c['command']=='download'])==2

@pytest.mark.parametrize('failure',['fail_list','malformed_list'])
def test_failed_snapshot_keeps_previous(api,failure):
    api.sync();old=api.engine.db['synced_at']
    api.modify(**{failure:True})
    j=api.start('sync')
    assert j['state']=='failed'
    assert api.engine.db['synced_at']==old
    assert api.client.get('/api/ads').json['ads'][0]['online']
    assert api.engine.db['sync_error']

def test_empty_account_is_not_stale(api):
    api.sync();api.modify(online=[])
    assert api.start('sync')['state']=='success'
    assert api.engine.db['online']==[]
    assert api.client.get('/api/ads').json['ads'][0]['state']=='not-in-snapshot'

def test_failed_download_visible_even_exit_zero(api):
    api.modify(fail_download='101')
    j=api.start('sync')
    assert j['state']=='failed'
    rows=api.client.get('/api/ads').json['ads']
    assert rows[0]['path'] is None
    assert api.engine.db['sync_error']

def test_resync_preserves_local_changes(api):
    name=api.sync()[0]['path'];d=api.client.get('/api/file?path='+name).json
    d['data']['title']='Edited locally'
    assert api.send('/api/file',{'path':name,'data':d['data'],'revision':d['revision']},'PUT').status_code==200
    api.sync()
    assert api.store.read(name)[0]['title']=='Edited locally'
    assert len([c for c in api.calls() if c['command']=='download'])==1

def test_form_keeps_unknown_fields(api):
    name=api.sync()[0]['path'];d=api.client.get('/api/file?path='+name).json
    d['data']['title']='New title'
    assert api.send('/api/file',{'path':name,'data':d['data'],'revision':d['revision']},'PUT').status_code==200
    assert api.store.read(name)[0]['special_attributes']['condition_s']=='like_new'
    assert api.store.read(name)[0]['contact']['zipcode']=='01234'

def test_upload_relative_to_nested_ad_and_webp_conversion(api):
    name=api.sync()[0]['path']
    b=BytesIO();Image.new('RGB',(10,10),'green').save(b,format='WEBP');b.seek(0)
    r=api.client.post('/api/images',headers=api.headers,data={'path':name,'files':(b,'test.webp')},content_type='multipart/form-data')
    assert r.status_code==200,r.json
    assert r.json['paths'][0].startswith('images/') and r.json['paths'][0].endswith('.jpg')
    image=api.store.path(name).parent/r.json['paths'][0]
    with Image.open(image) as im:
        assert im.format=='JPEG'

@pytest.mark.parametrize('raw',[b'not an image',b'\x89PNG\r\n\x1a\nTEST'])
def test_invalid_upload_rejected(api,raw):
    name=api.sync()[0]['path']
    r=api.client.post('/api/images',headers=api.headers,data={'path':name,'files':(BytesIO(raw),'fake.png')},content_type='multipart/form-data')
    assert r.status_code==400

def test_missing_images_block_publish(api):
    name=api.sync()[0]['path']
    obj,_=api.store.read(name)
    api.store.image_files(name,obj)[0].unlink()
    j=api.start('publish',name)
    assert j['state']=='failed'
    assert not any(c['command']=='publish' for c in api.calls())

def test_update_uses_single_scoped_ad(api):
    name=api.sync()[0]['path'];d=api.client.get('/api/file?path='+name).json
    d['data']['title']='Updated online'
    api.send('/api/file',{'path':name,'data':d['data'],'revision':d['revision']},'PUT')
    j=api.start('update',name)
    assert j['state']=='success',j
    calls=[c for c in api.calls() if c['command']=='update']
    assert calls[0]['args']['--ads']=='101'
    assert Path(calls[0]['args']['--config']).parent==api.store.work
    assert not list(api.store.work.glob('.job-config-*'))
    assert api.engine.db['online'][0]['title']=='Updated online'

def test_republish_new_id_same_data_images_and_archive(api):
    name=api.sync()[0]['path'];before=api.store.read(name)[0]
    j=api.start('publish',name)
    assert j['state']=='success',j
    after=api.store.read(name)[0]
    assert after['id']!=before['id']
    for key in ['title','description','category','price','images','contact','special_attributes']:
        assert after[key]==before[key]
    assert len(api.engine.db['online'])==1
    assert not any(a['ad_id']=='101' for a in api.engine.db['online'])
    assert list((api.store.state/'archives').rglob('restore.yaml'))
    assert list((api.store.state/'archives').rglob('image_000.png'))

def test_reserved_not_republished(api):
    name=api.sync()[0]['path'];assert api.start('reserve',name)['state']=='success'
    assert api.start('publish',name)['state']=='failed'
    assert api.engine.db['online'][0]['state']=='reserved'
    assert api.start('activate',name)['state']=='success'

def test_duplicate_id_blocks_action(api):
    name=api.sync()[0]['path'];obj,text=api.store.read(name)
    from storage import atomic_write
    atomic_write(api.store.work/'ads/duplicate.yaml',text)
    assert api.start('update',name)['state']=='failed'
    assert not any(c['command']=='update' for c in api.calls())

def test_split_secrets_redacted_and_history_persisted(api):
    j=api.start('status')
    assert j['state']=='success'
    assert '[VERBORGEN]' in j['output']
    assert 'offline-secret-123456789' not in j['output']
    r=api.client.get('/api/log/'+j['id']);assert b'offline-secret' not in r.data;r.close()
    db=json.loads(api.engine.db_path.read_text())
    assert db['history'][-1]['state']=='success'

def test_pty_login_locks_edits_and_enter(api):
    assert api.send('/api/jobs',{'command':'login'}).status_code==202
    for _ in range(200):
        if api.engine.current['pty'] is not None:
            break
        time.sleep(.01)
    assert api.send('/api/jobs',{'command':'verify'}).status_code==409
    assert api.send('/api/file',{'path':'ads/new.yaml','content':'title: New'},'PUT').status_code==409
    assert api.send('/api/jobs/enter',{}).status_code==200
    assert api.wait_done()['state']=='success'

def test_stop_process_group(api):
    api.send('/api/jobs',{'command':'diagnose'})
    for _ in range(200):
        if (api.store.work/'.child-pid').exists():
            break
        time.sleep(.01)
    assert api.send('/api/jobs/stop',{}).status_code==200
    assert api.wait_done()['state']=='stopped'
    pid=int((api.store.work/'.child-pid').read_text())
    status=Path('/proc')/str(pid)/'status'
    if status.exists():
        assert re.search(r'^State:\s+Z',status.read_text(),re.M)

def test_timeout(api):
    api.engine.timeout=.15
    assert api.start('diagnose')['state']=='timeout'

def test_initial_sync_if_idle_no_duplicate(api):
    r=api.send('/api/jobs',{'command':'sync','if_idle':True});assert r.status_code==202
    r=api.send('/api/jobs',{'command':'sync','if_idle':True});assert r.status_code==202
    api.wait_done()
    assert len([c for c in api.calls() if c['command']=='list'])==1
    assert api.send('/api/jobs',{'command':'sync','if_idle':True}).json['skipped']


def test_online_refresh_preserves_path_policy_images_and_counters(api):
    name=api.sync()[0]['path']
    api.engine.set_policy(name,True,17,True)
    original_policy=dict(api.engine.db['policies'][name])
    obj,text=api.store.read(name)
    obj['title']='Local unsynced title';obj['republication_interval']=17;obj['repost_count']=8
    from storage import atomic_write
    import yaml
    atomic_write(api.store.path(name),yaml.safe_dump(obj))
    api.modify(online=[dict(id=101,title='Updated externally',state='active',expires='-')])
    done=api.start('refresh',name)
    assert done['state']=='success',done
    new,_=api.store.read(name)
    assert new['title']=='Updated externally'
    assert new['republication_interval']==17 and new['repost_count']==8
    assert api.engine.db['policies'][name]==original_policy
    assert new['images'][0].startswith('images/online-')
    assert api.store.image_files(name,new,strict=True)
    assert not list(api.store.work.glob('refresh-*'))
    assert len([f for f in api.store.files() if f.get('ad_id')=='101'])==1


def test_failed_online_refresh_leaves_original_untouched(api):
    name=api.sync()[0]['path'];before=api.store.path(name).read_bytes()
    api.modify(fail_download='101')
    assert api.start('refresh',name)['state']=='failed'
    assert api.store.path(name).read_bytes()==before
    assert not list(api.store.work.glob('refresh-*'))


def test_supervisor_token_not_in_child_environment(api):
    api.start('version')
    assert api.calls()[0]['supervisor_present'] is False


def test_external_image_and_image_symlinks_rejected(api):
    name=api.sync()[0]['path']
    image=api.store.work/'ads/leak.jpg'
    image.symlink_to('/etc/passwd')
    assert api.client.get('/api/image?path=ads/leak.jpg').status_code==400
    obj,_=api.store.read(name);obj['images']=['/etc/passwd']
    from storage import Invalid
    with pytest.raises(Invalid):
        api.store.image_files(name,obj,strict=True)


def test_invalid_oversized_request(api):
    r=api.client.post('/api/jobs',headers={**api.headers,'Content-Type':'application/json'},data=b' '*(20*1024*1024+1))
    assert r.status_code==413


def test_native_yaml_timestamps_survive_form_edit(api):
    name=api.sync()[0]['path'];obj,_=api.store.read(name)
    from datetime import datetime
    import yaml
    from storage import atomic_write
    obj['updated_on']=datetime(2026,1,1,12,0,0)
    atomic_write(api.store.path(name),yaml.safe_dump(obj))
    d=api.client.get('/api/file?path='+name).json
    assert d['data']['updated_on']=='2026-01-01T12:00:00'
    d['data']['title']='Edited with YAML timestamp'
    r=api.send('/api/file',{'path':name,'data':d['data'],'revision':d['revision']},'PUT')
    assert r.status_code==200,r.json


@pytest.mark.parametrize('path',['./ads/x.yaml','ads//x.yaml','ads/./x.yaml'])
def test_path_aliases_cannot_create_duplicate_policies(api,path):
    assert api.client.get('/api/file',query_string={'path':path}).status_code==400


def test_crlf_config_revision_can_be_saved(api):
    p=api.store.work/'config.yaml'
    p.write_bytes(p.read_bytes().replace(b'\n',b'\r\n'))
    d=api.client.get('/api/config').json
    r=api.send('/api/config',d,'PUT')
    assert r.status_code==200,r.json

@pytest.mark.parametrize('command',[[],{},42,None])
def test_command_type_validated(api,command):
    assert api.send('/api/jobs',{'command':command}).status_code==400
