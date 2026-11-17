"""Exercise the installed application, auth boundary, storage and local Ansible.

Run with the installed private Python. Uses a temporary SQLite/state directory;
never contacts managed hosts and never changes the installed live database.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if Path('/opt/fleetops/backend').exists():
    ROOT = Path('/opt/fleetops')
state = tempfile.TemporaryDirectory(prefix='fleetops-smoke-')
os.environ['FLEETOPS_DATA_DIR'] = state.name
os.environ['FLEETOPS_DATABASE_URL'] = 'sqlite:///' + state.name + '/test.db'
os.environ['FLEETOPS_CONFIG'] = state.name + '/missing.conf'
os.environ['FLEETOPS_SECRET_KEY'] = 'test-session-secret'
os.environ['PATH'] = '/opt/fleetops/venv/bin:' + os.environ.get('PATH', '')
sys.path.insert(0, str(ROOT / 'backend'))

from app import app, socketio, PLAYBOOKS, INVENTORY, save_schedules, load_schedules
from models import db, create_default_roles
from auth import create_user


class RuntimeSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        with app.app_context():
            create_default_roles(app)
            for name, role in [('admin-test', 'admin'), ('viewer-test', 'viewer')]:
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
