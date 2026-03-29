"""
Integration tests for Maytag Admin Console authentication.
"""

import pytest
import os
import tempfile
from datetime import datetime

from backend.models import db, User, Role, Permission, AuditLog, Secret
from backend.auth import authenticate_local, create_user
from backend.vault import SecretsVault


@pytest.fixture
def app():
    """Create app for testing."""
    from backend.app import create_app
    
    db_fd, db_path = tempfile.mkstemp()
    app = create_app()
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    with app.app_context():
        db.create_all()
        _create_test_data()

    yield app

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


def _create_test_data():
    """Create default test data."""
    admin_role = Role(name='admin', description='Admin')
    operator_role = Role(name='operator', description='Operator')
    viewer_role = Role(name='viewer', description='Viewer')

    perms = [
        Permission(resource='ansible', action='view_playbooks'),
        Permission(resource='ansible', action='execute_playbook'),
        Permission(resource='admin', action='manage_users'),
        Permission(resource='admin', action='manage_secrets'),
    ]

    admin_role.permissions = perms
    operator_role.permissions = perms[:2]
    viewer_role.permissions = [perms[0]]

    db.session.add_all([admin_role, operator_role, viewer_role] + perms)
    db.session.commit()


class TestAuthentication:
    """Test authentication functionality."""

    def test_create_local_user(self, app):
        """Test creating a local user."""
        with app.app_context():
            user, msg = create_user('testuser', 'test@example.com', 'Password123')
            assert user is not None
            assert user.username == 'testuser'

    def test_authenticate_local_user(self, app):
        """Test authenticating a local user."""
        with app.app_context():
            create_user('testuser', 'test@example.com', 'Password123')
            user, msg = authenticate_local('testuser', 'Password123')
            assert user is not None

    def test_authenticate_invalid_password(self, app):
        """Test authentication with invalid password."""
        with app.app_context():
            create_user('testuser', 'test@example.com', 'Password123')
            user, msg = authenticate_local('testuser', 'WrongPassword')
            assert user is None


class TestRBAC:
    """Test Role-Based Access Control."""

    def test_user_has_role(self, app):
        """Test checking user role."""
        with app.app_context():
            user = User(username='u', email='u@example.com', auth_method='local')
            role = Role.query.filter_by(name='admin').first()
            user.roles.append(role)
            db.session.add(user)
            db.session.commit()

            assert user.has_role('admin')

    def test_user_has_permission(self, app):
        """Test checking user permission."""
        with app.app_context():
            user = User(username='u', email='u@example.com', auth_method='local')
            role = Role.query.filter_by(name='admin').first()
            user.roles.append(role)
            db.session.add(user)
            db.session.commit()

            assert user.has_permission('ansible', 'view_playbooks')


class TestSecretsVault:
    """Test secrets encryption."""

    def test_encrypt_decrypt(self):
        """Test encryption and decryption."""
        vault = SecretsVault()
        plaintext = "super_secret_key_12345"
        encrypted = vault.encrypt(plaintext)
        decrypted = vault.decrypt(encrypted)
        assert decrypted == plaintext
