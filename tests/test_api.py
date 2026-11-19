# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline API and PTY tests. No calls to Kleinanzeigen or GitHub."""
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FAKE_SOURCE = """#!/usr/bin/env python3
import os, sys, time
command = sys.argv[1]
print('FAKE ' + command, flush=True)
secret = os.environ.get('KLEINANZEIGEN_BOT_PASSWORD', '')
if command == 'status':
    mid = len(secret) // 2
    sys.stdout.write('Private: ' + secret[:mid]); sys.stdout.flush()
    time.sleep(.1)
    print(secret[mid:] + '\\n' + 'x' * 100, flush=True)
else:
    print('Private: ' + secret, flush=True)
if command == 'login':
    print('ENTER please', flush=True)
    input()
if command == 'diagnose':
    time.sleep(60)
if command == 'list':
    sys.exit(1)
print('DONE', flush=True)
"""

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='ha-kleinanzeigen-test-')
        cls.directory = Path(cls.tmp.name)
        fake = cls.directory / 'fake_bot.py'
        fake.write_text(FAKE_SOURCE)
        fake.chmod(0o755)
        cls.env = patch.dict(os.environ, {
            'BOT_WORKSPACE': str(cls.directory / 'workspace'),
            'BOT_STATE': str(cls.directory / 'state'),
            'BOT_BINARY': str(fake),
            'JOB_TIMEOUT_MINUTES': '1',
        })
        cls.env.start()
        spec = importlib.util.spec_from_file_location('ha_addon_api_test', ROOT / 'kleinanzeigen_bot/app/server.py')
        cls.server = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.server
        spec.loader.exec_module(cls.server)
        cls.client = cls.server.app.test_client()
        cls.headers = {'X-CSRF-Token': cls.server.CSRF}

    @classmethod
    def tearDownClass(cls):
        if cls.server.current and cls.server.current['state'] == 'running':
            cls.server.current['stop_requested'] = True
            for _ in range(300):
                if cls.server.current['state'] != 'running':
                    break
                time.sleep(.03)
        cls.env.stop()
        cls.tmp.cleanup()

    def setUp(self):
        if self.server.current and self.server.current['state'] == 'running':
            self.wait_done()
        self.server.atomic_write(self.server.WORK / 'config.yaml', self.server.DEFAULT_CONFIG)
        self.server.atomic_write(self.server.WORK / '.credentials.json', json.dumps({
            'username': 'offline@example.invalid', 'password': 'offline-secret-123456789'}))

    def send(self, path, data, method='POST'):
        return self.client.open(path, method=method, json=data, headers=self.headers)

    def start(self, command, selector='', **kwargs):
        response = self.send('/api/jobs', dict(command=command, selector=selector, **kwargs))
        self.assertEqual(response.status_code, 202, response.get_data(as_text=True))
        return response.json['job']['id']

    def wait_done(self):
        for _ in range(300):
            job = self.client.get('/api/status').json['current']
            if job['state'] != 'running':
                return job
            time.sleep(.03)
        self.fail('Fake bot did not terminate')

    def wait_pty(self):
        for _ in range(100):
            if self.server.current['pty'] is not None:
                return
            time.sleep(.02)
        self.fail('PTY not ready')

    def test_homepage(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Browserdesktop', r.data)
        self.assertNotIn(b'{{ csrf', r.data)

    def test_csrf(self):
        r = self.client.post('/api/jobs', json={'command': 'verify'})
        self.assertEqual(r.status_code, 403)

    def test_json_object_required(self):
        self.assertEqual(self.send('/api/jobs', ['verify']).status_code, 400)

    def test_credentials_private(self):
        r = self.client.get('/api/credentials')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('password', r.json)
        self.assertTrue(r.json['password_set'])
        self.assertEqual((self.server.WORK / '.credentials.json').stat().st_mode & 0o777, 0o600)

    def test_password_preserved(self):
        self.assertEqual(self.send('/api/credentials', {'username':'new@example.invalid', 'password':''}, 'PUT').status_code, 200)
        self.assertEqual(self.server.credentials()['password'], 'offline-secret-123456789')

    def test_ad_crud(self):
        data={'path':'ads/ad_crud.yaml', 'content':'active: false\ntitle: Offline test\nprice: 10\n'}
        self.assertEqual(self.send('/api/file', data, 'PUT').status_code, 200)
        self.assertEqual(self.client.get('/api/file?path=ads/ad_crud.yaml').json['content'], data['content'])
        self.assertEqual(self.send('/api/file', {'path':data['path']}, 'DELETE').status_code, 400)
        self.assertEqual(self.send('/api/file', {'path':data['path'], 'confirm':True}, 'DELETE').status_code, 200)
        self.assertEqual(self.client.get('/api/file?path=ads/ad_crud.yaml').status_code, 404)
        self.assertTrue(list((self.server.STATE / 'backups').glob('*.bak')))

    def test_file_listing(self):
        self.assertEqual(self.send('/api/file', {'path':'ads/ad_listing.yaml','content':'title: List test\n'}, 'PUT').status_code, 200)
        self.assertIn('ads/ad_listing.yaml',[f['path'] for f in self.client.get('/api/files').json['files']])

    def test_path_traversal(self):
        for path in ['ads/../../options.json','/etc/passwd','ads/.credentials.json','ads/ad_bad.txt','config.yaml']:
            self.assertEqual(self.client.get('/api/file',query_string={'path':path}).status_code,400,path)

    def test_symlink(self):
        link = self.server.WORK / 'ads/ad_link.yaml'
        link.symlink_to(self.server.WORK / 'config.yaml')
        try:
            self.assertEqual(self.client.get('/api/file?path=ads/ad_link.yaml').status_code, 400)
        finally:
            link.unlink()

    def test_yaml_invalid(self):
        self.assertEqual(self.send('/api/config',{'content':'login: ['},'PUT').status_code,400)
        self.assertEqual(self.send('/api/config',{'content':'[]'},'PUT').status_code,400)
        self.assertEqual(self.send('/api/config',{'content':'browser: {}'},'PUT').status_code,400)

    def test_json_file_invalid(self):
        self.assertEqual(self.send('/api/file',{'path':'ads/ad_invalid.json','content':'title: not JSON'},'PUT').status_code,400)

    def test_confirmation_required(self):
        for command in self.server.MUTATING:
            self.assertEqual(self.send('/api/jobs',{'command':command,'selector':'all'}).status_code,400)

    def test_command_injection(self):
        for data in [{'command':'sh','selector':''}, {'command':'publish','selector':'all; echo unsafe','confirm':True}, {'command':'verify','selector':'all'}]:
            self.assertEqual(self.send('/api/jobs',data).status_code,400)

    def test_publish_arguments(self):
        with self.server.app.test_request_context('/'):
            cmd, sel, args=self.server.validate_job({'command':'publish','selector':'changed,due','confirm':True,'keep_old':True})
        self.assertEqual(sel,'changed,due')
        self.assertIn('--keep-old',args)
        self.assertIn('--workspace-mode=portable',args)

    def test_job_success_and_log(self):
        job_id=self.start('verify')
        job=self.wait_done()
        self.assertEqual(job['state'],'success')
        self.assertEqual(job['returncode'],0)
        self.assertIn('[VERBORGEN]',job['output'])
        self.assertNotIn('offline-secret-123456789',job['output'])
        r=self.client.get('/api/log/'+job_id)
        self.assertEqual(r.status_code,200)
        self.assertNotIn(b'offline-secret-123456789',r.data)
        r.close()

    def test_job_failure(self):
        self.start('list')
        self.assertEqual(self.wait_done()['state'],'failed')

    def test_login_pty_lock_and_enter(self):
        self.start('login')
        self.wait_pty()
        self.assertEqual(self.send('/api/jobs',{'command':'verify'}).status_code,409)
        self.assertEqual(self.send('/api/config',{'content':self.server.DEFAULT_CONFIG},'PUT').status_code,409)
        self.assertEqual(self.send('/api/credentials',{'username':'x','password':'y'},'PUT').status_code,409)
        self.assertEqual(self.send('/api/jobs/enter',{}).status_code,200)
        self.assertEqual(self.wait_done()['state'],'success')

    def test_stop(self):
        self.start('diagnose')
        self.wait_pty()
        self.assertEqual(self.send('/api/jobs/stop',{}).status_code,200)
        self.assertEqual(self.wait_done()['state'],'stopped')

    def test_timeout(self):
        old=self.server.TIMEOUT
        self.server.TIMEOUT=.15
        try:
            self.start('diagnose')
            self.assertEqual(self.wait_done()['state'],'timeout')
        finally:
            self.server.TIMEOUT=old

    def test_split_secret_redacted(self):
        self.start('status')
        j=self.wait_done()
        self.assertNotIn('offline-secret-123456789',j['output'])
        self.assertIn('[VERBORGEN]',j['output'])

    def test_png_upload(self):
        r=self.client.post('/api/images',headers=self.headers,
                           data={'files':(BytesIO(b'\x89PNG\r\n\x1a\nTEST'),'test.png')},content_type='multipart/form-data')
        self.assertEqual(r.status_code,200)
        self.assertTrue((self.server.WORK / 'ads' / r.json['paths'][0]).is_file())

    def test_upload_invalid(self):
        r=self.client.post('/api/images',headers=self.headers,
                           data={'files':(BytesIO(b'<script>'),'test.png')},content_type='multipart/form-data')
        self.assertEqual(r.status_code,400)

    def test_finished_job_persisted(self):
        self.start('verify');j=self.wait_done()
        h=json.loads((self.server.STATE / 'history.json').read_text())
        self.assertEqual(h[-1]['id'],j['id'])
        self.assertEqual(h[-1]['state'],'success')
        self.assertEqual(sum(item['id']==j['id'] for item in h),1)

if __name__ == '__main__':
    unittest.main(verbosity=2)
