"""Exercise the installed application, auth boundary, storage and local Ansible.

Run with the installed private Python. Uses a temporary SQLite/state directory;
never contacts managed hosts and never changes the installed live database.
"""
import os
import sys
import tempfile
import unittest
import subprocess
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if Path('/opt/fleetops/backend').exists() and not os.environ.get('FLEETOPS_TEST_SOURCE'):
    ROOT = Path('/opt/fleetops')
state = tempfile.TemporaryDirectory(prefix='fleetops-smoke-')
os.environ['FLEETOPS_DATA_DIR'] = state.name
os.environ['FLEETOPS_DATABASE_URL'] = 'sqlite:///' + state.name + '/test.db'
os.environ['FLEETOPS_CONFIG'] = state.name + '/missing.conf'
os.environ['FLEETOPS_SECRET_KEY'] = 'test-session-secret'
os.environ['PATH'] = '/opt/fleetops/venv/bin:' + os.environ.get('PATH', '')
sys.path.insert(0, str(ROOT / 'backend'))

from cryptography.fernet import Fernet
os.environ['FLEETOPS_VAULT_KEY_FILE'] = state.name + '/persistent-vault.key'
Path(os.environ['FLEETOPS_VAULT_KEY_FILE']).write_bytes(Fernet.generate_key())

from app import app, socketio, PLAYBOOKS, INVENTORY, save_schedules, load_schedules
from models import db, create_default_roles
from auth import create_user


class RuntimeSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        with app.app_context():
            create_default_roles(app)
            for name, role in [('admin-test', 'admin'), ('viewer-test', 'viewer'), ('operator-test', 'operator')]:
                user, message = create_user(name, name + '@example.com', 'Password123', roles=[role])
                assert user is not None, message

    def login(self, name='admin-test'):
        client = app.test_client()
        response = client.post('/auth/login', json={'username': name, 'password': 'Password123', 'auth_method': 'local'})
        self.assertEqual(response.status_code, 200, response.data)
        return client

    def test_help_about_health_and_assets(self):
        client = app.test_client()
        for route in ['/help', '/about', '/healthz', '/vendor/fleetops.svg', '/vendor/xterm/xterm.js']:
            response = client.get(route)
            self.assertEqual(response.status_code, 200, route)
            response.close()
        self.assertEqual(client.get('/healthz').json['application'], 'FleetOps')

    def test_anonymous_operations_and_socket_denied(self):
        client = app.test_client()
        self.assertEqual(client.get('/api/dashboard').status_code, 401)
        self.assertEqual(client.post('/api/adhoc', json={}).status_code, 401)
        response = client.get('/auth/me')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])
        ws = socketio.test_client(app, namespace='/ssh', flask_test_client=client)
        self.assertFalse(ws.is_connected('/ssh'))

    def test_login_admin_and_viewer_permissions(self):
        admin = self.login()
        self.assertEqual(admin.get('/auth/me').status_code, 200)
        self.assertEqual(admin.get('/admin/users').status_code, 200)
        viewer = self.login('viewer-test')
        self.assertEqual(viewer.get('/api/dashboard').status_code, 200)
        self.assertEqual(viewer.post('/api/playbooks/run', json={}).status_code, 403)
        self.assertEqual(viewer.get('/admin/users').status_code, 403)

    def test_local_playbook_and_persistent_schedule_file(self):
        client = self.login()
        playbook = '- hosts: all\n  gather_facts: false\n  tasks:\n    - ansible.builtin.debug:\n        msg: FleetOps-offline-smoke\n'
        self.assertEqual(client.put('/api/playbooks/smoke.yml', json={'content': playbook}).status_code, 200)
        self.assertTrue(client.post('/api/playbooks/validate', json={'content': playbook}).json['valid'])
        INVENTORY.joinpath('local.ini').write_text('localhost ansible_connection=local\n')
        response = client.post('/api/playbooks/run', json={'playbook': 'smoke.yml', 'inventory': 'local.ini'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.json['success'], response.json)
        self.assertIn('FleetOps-offline-smoke', response.json['stdout'])
        schedule = [{'id': 'paused-test', 'name': 'Test', 'playbook': 'smoke.yml', 'inventory': 'local.ini', 'cron': '0 2 * * *', 'enabled': False}]
        save_schedules(schedule)
        self.assertEqual(load_schedules(), schedule)

    def test_vault_persistent_key(self):
        from cryptography.fernet import Fernet
        from vault import SecretsVault
        keyfile = Path(state.name) / 'vault.key'
        keyfile.write_bytes(Fernet.generate_key())
        os.environ['FLEETOPS_VAULT_KEY_FILE'] = str(keyfile)
        first = SecretsVault()
        ciphertext = first.encrypt('offline secret')
        self.assertEqual(SecretsVault().decrypt(ciphertext), 'offline secret')

    def test_ssh_credentials_encryption_ownership_and_server_side_reuse(self):
        from models import SSHCredential
        admin, operator = self.login(), self.login('operator-test')
        secret = 'Synthetic-test-password-419!'
        payload = dict(label='Vault smoke', host='vault-smoke.example', port=2222, username='ssh-smoke-user', password=secret)
        created = admin.post('/api/ssh-credentials', json=payload)
        self.assertEqual(created.status_code, 201, created.data)
        credential_id = created.json['id']
        self.assertNotIn(secret, created.get_data(as_text=True))
        listed = admin.get('/api/ssh-credentials')
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn(secret, listed.get_data(as_text=True))
        self.assertNotIn('password', listed.get_data(as_text=True))
        self.assertEqual(operator.get('/api/ssh-credentials').json, [])
        self.assertEqual(operator.delete('/api/ssh-credentials/' + str(credential_id)).status_code, 404)
        self.assertEqual(self.login('viewer-test').get('/api/ssh-credentials').status_code, 403)
        self.assertEqual(admin.post('/api/ssh-credentials', json=payload).status_code, 409)
        self.assertEqual(admin.post('/api/ssh-credentials', json=payload, headers={'Origin':'https://other.example'}).status_code, 403)
        with app.app_context():
            row = db.session.get(SSHCredential, credential_id)
            self.assertNotIn(secret.encode(), row.value_encrypted)
            self.assertNotIn(b'vault-smoke.example', row.value_encrypted)
            self.assertNotIn(b'ssh-smoke-user', row.value_encrypted)
        raw_db = Path(state.name, 'test.db').read_bytes()
        self.assertNotIn(secret.encode(), raw_db)
        self.assertNotIn(b'vault-smoke.example', raw_db)
        restart_code = '''import os,sqlite3,json
from flask import Flask
from vault import init_vault,get_vault
init_vault(Flask(__name__))
connection=sqlite3.connect(os.environ['FLEETOPS_DATA_DIR']+'/test.db')
value=connection.execute('select value_encrypted from ssh_credential where id=?', (int(os.environ['TEST_CREDENTIAL_ID']),)).fetchone()[0]
assert json.loads(get_vault().decrypt(value))['password']=='Synthetic-test-password-419!'
print('restored')'''
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'backend'), TEST_CREDENTIAL_ID=str(credential_id))
        self.assertEqual(subprocess.check_output([sys.executable, '-c', restart_code], env=env, text=True).strip(), 'restored')
        ws = socketio.test_client(app, namespace='/ssh', flask_test_client=admin)
        with patch('app.paramiko.SSHClient') as client_class:
            client_class.return_value.invoke_shell.side_effect = RuntimeError('Synthetic stop after connect')
            ws.emit('connect_ssh', {'credential_id':credential_id, 'host':'ignored.example'}, namespace='/ssh')
            args = client_class.return_value.connect.call_args
            self.assertEqual(args.args[0], payload['host'])
            self.assertEqual(args.kwargs['password'], secret)
            self.assertNotIn(secret, str(ws.get_received('/ssh')))
        ws.disconnect(namespace='/ssh')
        other_ws = socketio.test_client(app, namespace='/ssh', flask_test_client=operator)
        with patch('app.paramiko.SSHClient') as client_class:
            other_ws.emit('connect_ssh', {'credential_id':credential_id}, namespace='/ssh')
            client_class.assert_not_called()
        other_ws.disconnect(namespace='/ssh')
        self.assertEqual(admin.delete('/api/ssh-credentials/' + str(credential_id)).status_code, 200)
        self.assertEqual(admin.get('/api/ssh-credentials').json, [])
        with app.app_context():
            user, _ = create_user('disposable-test', 'disposable@example.com', 'Password123', roles=['operator'])
            disposable_id = user.id
        disposable = self.login('disposable-test')
        orphan_test = disposable.post('/api/ssh-credentials', json=dict(payload, label='Remove with owner'))
        self.assertEqual(orphan_test.status_code, 201)
        with app.app_context():
            from models import User
            db.session.delete(db.session.get(User, disposable_id))
            db.session.commit()
            self.assertIsNone(db.session.get(SSHCredential, orphan_test.json['id']))

    def test_vault_startup_requires_persistent_key(self):
        from flask import Flask
        from vault import init_vault
        env = dict(os.environ)
        env.pop('FLEETOPS_SECRETS_KEY', None)
        env['FLEETOPS_VAULT_KEY_FILE'] = state.name + '/does-not-exist.key'
        with patch.dict(os.environ, env, clear=True), self.assertRaises(RuntimeError):
            init_vault(Flask('missing-key-test'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
