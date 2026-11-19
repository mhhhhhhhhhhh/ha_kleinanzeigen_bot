# SPDX-License-Identifier: AGPL-3.0-or-later
"""Non-destructive offline project checks; optional JavaScript syntax check."""
import ast
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import yaml
ROOT=Path(__file__).resolve().parents[1]
for path in ROOT.rglob('*.py'):
    ast.parse(path.read_text())
    print('Python syntax OK:',path.relative_to(ROOT))
for path in ROOT.rglob('*.yaml'):
    yaml.safe_load(path.read_text())
    print('YAML syntax OK:',path.relative_to(ROOT))
config=yaml.safe_load((ROOT/'kleinanzeigen_bot/config.yaml').read_text())
assert config['ingress'] is True and config['ingress_port']==8099
assert config['arch']==['amd64','aarch64']
assert 'ports' not in config and 'host_network' not in config
assert set(config['schema'])==set(config['options'])
nginx=(ROOT/'kleinanzeigen_bot/nginx.conf').read_text()
assert 'allow 172.30.32.2;' in nginx and 'deny all;' in nginx
assert 'proxy_set_header Upgrade' in nginx
print('Ingress manifest, ACL and WebSocket directives: OK (static only)')
html=(ROOT/'kleinanzeigen_bot/app/templates/index.html').read_text()
assert '{{ csrf|tojson }}' in html
assert 'new URL(path,base)' in html
assert '<script src="https://' not in html
print('UI template and relative API paths: OK (static only)')
node=shutil.which('node')
if node:
    js=re.search(r'<script>(.*?)</script>',html,re.S).group(1)
    js=js.replace('{{ csrf|tojson }}','"test-csrf"')
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'ui.js';path.write_text(js)
        subprocess.run([node,'--check',str(path)],check=True)
    print('JavaScript syntax: OK')
else:
    print('SKIPPED: JavaScript engine not installed; UI browser execution remains untested.')
print('Not run: Docker build, nginx -t, Home Assistant Supervisor, real Chromium/noVNC or Kleinanzeigen.')
