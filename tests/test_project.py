# SPDX-License-Identifier: AGPL-3.0-or-later
import ast
from pathlib import Path
import re
import shutil
import subprocess
import json
from bs4 import BeautifulSoup
import jinja2
import pytest
import yaml
ROOT=Path(__file__).resolve().parents[1]


def test_all_python_compiles():
    for p in ROOT.rglob('*.py'):
        ast.parse(p.read_text(),filename=str(p))


def test_ui_ids_unique_and_all_js_references_exist():
    template=(ROOT/'kleinanzeigen_bot/app/templates/index.html').read_text()
    rendered=jinja2.Template(template).render(csrf='offline',ingress='/')
    soup=BeautifulSoup(rendered,'html.parser')
    ids=[x['id'] for x in soup.select('[id]')]
    assert len(ids)==len(set(ids))
    script=soup.find('script').string
    for ref in re.findall(r"\$\('([^']+)'\)",script):
        assert ref in ids,ref
    assert 'innerHTML' not in script


def test_ui_javascript_syntax():
    node=shutil.which('node')
    if not node:
        try:
            import playwright
            p=Path(playwright.__file__).parent/'driver/node'
            if p.exists():node=str(p)
        except ImportError:
            pass
    if not node:
        pytest.skip('Node is not installed')
    rendered=jinja2.Template((ROOT/'kleinanzeigen_bot/app/templates/index.html').read_text()).render(csrf='test',ingress='/prefix/')
    script=BeautifulSoup(rendered,'html.parser').find('script').string
    result=subprocess.run([node,'--check','-'],input=script,capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_home_assistant_manifest():
    cfg=yaml.safe_load((ROOT/'kleinanzeigen_bot/config.yaml').read_text())
    assert cfg['slug']=='ha_kleinanzeigen_bot'
    assert cfg['version']=='0.2.0'
    assert cfg['arch']==['amd64','aarch64']
    assert cfg['ingress'] is True and cfg['panel_admin'] is True
    assert cfg.get('ports') is None
    assert cfg['options']['desktop_width']>=1280


def test_docker_install_contract():
    text=(ROOT/'kleinanzeigen_bot/Dockerfile').read_text()
    assert 'python3-venv' in text and 'python3-pil' in text
    assert 'scripts/fix_nodriver.py' in text
    assert 'git rev-parse HEAD' in text
    assert 'kleinanzeigen-bot-linux-aarch64' not in text
    assert 'exec /opt/venv/bin/python -m kleinanzeigen_bot "$@"' in (ROOT/'kleinanzeigen_bot/bot-entry.sh').read_text()


def test_ingress_proxy_contract():
    text=(ROOT/'kleinanzeigen_bot/nginx.conf').read_text()
    assert 'allow 172.30.32.2;' in text and 'deny all;' in text
    assert 'proxy_set_header Upgrade $http_upgrade;' in text
    assert 'proxy_set_header X-Ingress-Path $http_x_ingress_path;' in text
    assert 'location /desktop/' in text


def test_source_contains_no_real_credentials():
    for p in ROOT.glob('kleinanzeigen_bot/app/*.py'):
        assert 'offline-secret' not in p.read_text()
