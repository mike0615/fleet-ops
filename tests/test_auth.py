"""
Integration tests for FleetOps authentication.
"""

import pytest
from models import db, User, Role, Permission, AuditLog, Secret
from auth import authenticate_local, create_user
from vault import SecretsVault


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
            user.set_password('Password123')
            role = Role.query.filter_by(name='admin').first()
            user.roles.append(role)
            db.session.add(user)
            db.session.commit()

            assert user.has_role('admin')

    def test_user_has_permission(self, app):
        """Test checking user permission."""
        with app.app_context():
            user = User(username='u', email='u@example.com', auth_method='local')
            user.set_password('Password123')
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
