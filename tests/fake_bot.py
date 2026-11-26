# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline CLI contract double. Never sends a network request."""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import yaml

work = Path.cwd()
control = work/'.fake-control.json'
data = json.loads(control.read_text())
command = sys.argv[1]
args = {a.split('=',1)[0]:a.split('=',1)[1] for a in sys.argv[2:] if '=' in a}
with (work/'.fake-calls.jsonl').open('a') as stream:
    stream.write(json.dumps(dict(command=command,args=args,argv=sys.argv,supervisor_present='SUPERVISOR_TOKEN' in os.environ))+'\n')
print('Offline CLI fixture', flush=True)
secret = os.environ.get('KLEINANZEIGEN_BOT_PASSWORD', '')
if command == 'status':
    middle = len(secret)//2
    print('Private: '+secret[:middle], end='', flush=True)
    time.sleep(.03)
    print(secret[middle:]+'\n'+'x'*200, flush=True)
else:
    print('Private: '+secret, flush=True)
if command == 'login':
    print('ENTER please',flush=True)
    input()
if command == 'diagnose':
    import subprocess
    child = subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)'])
    (work/'.child-pid').write_text(str(child.pid))
    time.sleep(90)
if command == 'list':
    if data.get('fail_list'):
        print('ID: 99\n  title: Partial',flush=True)
        sys.exit(1)
    if data.get('malformed_list'):
        print('ID: 99\n  title: Partial\n  status: active',flush=True)
        sys.exit(0)
    if not data['online']:
        print('No online ads found.',flush=True)
    for ad in data['online']:
        print(f"ID: {ad['id']}\n  title: {ad['title']}\n  status: {ad['state']}\n  expires: {ad.get('expires','-')}\n",flush=True)
if command == 'download':
    ids = args.get('--ads','').split(',')
    for ad_id in ids:
        if ad_id == data.get('fail_download'):
            print('DONE: downloaded 0 of 1 (1 failed)',flush=True)
            continue
        ad = next(x for x in data['online'] if str(x['id'])==ad_id)
        cfg = yaml.safe_load(Path(args['--config']).read_text())
        download_dir = Path(cfg.get('download',{}).get('dir','./downloaded-ads'))
        if not download_dir.is_absolute():
            download_dir = Path(args['--config']).parent/download_dir
        target = download_dir/('ad_'+ad_id)
        target.mkdir(parents=True,exist_ok=True)
        name = 'ad_'+ad_id
        image_name = name+'__img1.png'
        (target/image_name).write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAEAAAAAwCAIAAAAuKetIAAAAU0lEQVR4nO3PQQ3AIADAQEAsL9SgeCJ4XJb0FLRz3zP+bOmAVw1oDWgNaA1oDWgNaA1oDWgNaA1oDWgNaA1oDWgNaA1oDWgNaA1oDWgNaA1oDWgfQHkBxDQt9UAAAAAASUVORK5CYII='))
        obj = dict(id=int(ad_id),active=ad['state']=='active',title=ad['title'],description='Original description',
            category='161/278',price=42,price_type='NEGOTIABLE',images=[image_name],
            created_on='2026-01-01T00:00:00+01:00',updated_on='2026-01-01T00:00:00+01:00',
            special_attributes={'condition_s':'like_new'},contact={'zipcode':'01234'},content_hash='fixture')
        (target/(name+'.yaml')).write_text(yaml.safe_dump(obj,sort_keys=False))
if command in {'verify','publish','update','extend','reserve','activate','delete'}:
    cfg = yaml.safe_load(Path(args['--config']).read_text())
    selected = cfg['ad_files']
    if command == 'verify' and len(selected)!=1:
        print('DONE: verify all',flush=True)
        sys.exit(0)
    if command == 'extend':
        ids = {int(x) for x in args['--ads'].split(',')}
        for path in selected:
            entry = yaml.safe_load(Path(path).read_text())
            assert entry['id'] in ids
            ad = next(x for x in data['online'] if x['id']==entry['id'])
            ad['expires'] = '2027-02-01T00:00:00Z'
        control.write_text(json.dumps(data))
        print('DONE: extended',flush=True)
        sys.exit(0)
    if len(selected)!=1:
        print('ERROR: action not scoped',flush=True)
        sys.exit(1)
    p = Path(selected[0])
    obj = yaml.safe_load(p.read_text())
    if command == 'verify':
        if not obj.get('title') or not obj.get('description') or not obj.get('category'):
            sys.exit(1)
    elif command == 'publish':
        if data.get('fail_publish'):
            sys.exit(1)
        old_id = obj.get('id')
        new_id = max([int(x['id']) for x in data['online']]+[1000])+1
        data['online'].append(dict(id=new_id,title=obj['title'],state='active',expires='2027-01-01T00:00:00Z'))
        if data.get('uncertain_publish'):
            control.write_text(json.dumps(data))
            print('Submission possibly successful',flush=True)
            sys.exit(1)
        if old_id:
            data['online'] = [x for x in data['online'] if x['id'] != old_id]
        if not data.get('same_id'):
            obj['id'] = new_id
        obj['updated_on'] = datetime.now(timezone.utc).isoformat()
        obj['repost_count'] = obj.get('repost_count',0)+1
        p.write_text(yaml.safe_dump(obj,sort_keys=False))
    else:
        ad = next(x for x in data['online'] if x['id']==obj['id'])
        if command == 'update':
            ad['title'] = obj['title']
        elif command == 'reserve':
            ad['state'] = 'reserved'
        elif command == 'activate':
            ad['state'] = 'active'
        elif command == 'extend':
            ad['expires'] = '2027-02-01T00:00:00Z'
        elif command == 'delete':
            data['online'].remove(ad)
    control.write_text(json.dumps(data))
print('DONE',flush=True)
