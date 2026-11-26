#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apply to an existing 0.2.x add-on SOURCE directory. No account actions."""
import argparse
import ast
from datetime import datetime
from pathlib import Path
import re
import shutil

parser=argparse.ArgumentParser()
parser.add_argument('addon',type=Path,help='Existing folder containing Dockerfile, config.yaml and app/server.py')
args=parser.parse_args()
folder=args.addon.resolve()
server=folder/'app/server.py'
engine=folder/'app/engine.py'
if not server.is_file() or not engine.is_file():
    raise SystemExit('Abbruch: bestehende 0.2.x-Server-/Engine-Dateien fehlen. Keine Dateien geändert.')
source=server.read_text()
ast.parse(source)
if not re.search(r'^engine\s*=\s*Engine\(',source,re.M):
    raise SystemExit('Abbruch: server.py verwendet nicht die 0.2.x Engine. Repository enthält möglicherweise gemischte Versionen. Keine Dateien geändert.')
if 'from sync_hotfix import install' not in source:
    marker=re.search(r"^if __name__\s*==\s*['\"]__main__['\"]\s*:",source,re.M)
    if not marker:raise SystemExit('Server-Einstieg nicht erkannt; keine Dateien geändert.')
    source=source[:marker.start()]+'from sync_hotfix import install as install_sync_hotfix\ninstall_sync_hotfix(engine, app)\n\n'+source[marker.start():]
ast.parse(source)
changes={server:source}
for filename in ['sync_hotfix.py','account_bridge.py']:
    content=(Path(__file__).parent/'app'/filename).read_text()
    ast.parse(content)
    changes[folder/'app'/filename]=content
for filename in ['config.yaml','Dockerfile']:
    p=folder/filename
    if not p.is_file():raise SystemExit(f'{filename} fehlt; keine Dateien geändert.')
    text=p.read_text()
    if filename=='config.yaml':
        text,count=re.subn(r'(?m)^version:\s*[^\n]+','version: "0.2.4"',text)
    else:
        text,count=re.subn(r'(?m)^ARG BUILD_VERSION=[^\n]+','ARG BUILD_VERSION=0.2.4',text)
    if count!=1:raise SystemExit(f'Versionsfeld in {filename} nicht eindeutig; keine Dateien geändert.')
    changes[p]=text
backup=folder.parent/(folder.name+'-before-hotfix-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
backup.mkdir()
for p,text in changes.items():
    if p.exists():
        target=backup/p.relative_to(folder);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    temporary=p.with_name(p.name+'.hotfix-tmp');temporary.write_text(text);temporary.replace(p)
print('Hotfix 0.2.4 angewendet:',folder)
print('Sicherung geänderter Dateien:',backup)
print('Jetzt Add-on-Image neu bauen, starten und Oberfläche neu laden. /data und Browserprofil bleiben unverändert.')
