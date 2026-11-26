#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Repeat the complete local test suite ten times; keep actual results."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parents[1]
results=root/'.test-results'
results.mkdir(exist_ok=True)
records=[]
for number in range(1,11):
    print(f'Prüfdurchlauf {number}/10',flush=True)
    start=time.monotonic()
    p=subprocess.run([sys.executable,'-m','pytest','tests','-q','--color=no'],cwd=root,text=True,capture_output=True)
    output=p.stdout+p.stderr
    (results/f'round-{number:02d}.txt').write_text(output)
    print(output,flush=True)
    records.append(dict(round=number,returncode=p.returncode,seconds=round(time.monotonic()-start,2)))
(results/'results.json').write_text(json.dumps(records,indent=2))
print('Ergebnisdateien:',results)
sys.exit(0 if all(r['returncode']==0 for r in records) else 1)
