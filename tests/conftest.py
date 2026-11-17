import os
from cryptography.fernet import Fernet
os.environ.setdefault("FLEETOPS_SECRETS_KEY", Fernet.generate_key().decode())
"""
Pytest configuration for FleetOps tests.
"""

import pytest
import sys
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

# Suppress logging during tests
import logging
logging.disable(logging.CRITICAL)


@pytest.fixture
def app(monkeypatch):
    """Create app for testing."""
    from app import create_app
    import models
    
    # Create fresh app for this test
    app = create_app(testing=True)
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    with app.app_context():
        # Get the db instance from the app's extensions
        if 'sqlalchemy' in app.extensions:
            db = app.extensions['sqlalchemy']
        else:
            from models import db
        
        # Monkeypatch the models db to use the test db
        monkeypatch.setattr(models, 'db', db)
        
        db.create_all()
        _create_test_data(db)

    yield app
    
    # Cleanup
    with app.app_context():
        if 'sqlalchemy' in app.extensions:
            db = app.extensions['sqlalchemy']
        else:
            from models import db
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


def _create_test_data(db):
    """Create default test data."""
    import json
    from models import Role, Permission, AuditLog
    
    admin_role = Role(name='admin', description='Admin')
    operator_role = Role(name='operator', description='Operator')
    viewer_role = Role(name='viewer', description='Viewer')
    
    # Create permissions with resource and action
    admin_perm = Permission(resource='ansible', action='view_playbooks', description='Admin access')
    read_perm = Permission(resource='ansible', action='read', description='Read-only')
    
    admin_role.permissions.append(admin_perm)
    admin_role.permissions.append(read_perm)
    operator_role.permissions.append(read_perm)
    
    audit = AuditLog(
        user_id=None,
        action='TEST_INIT',
        resource='test',
        details=json.dumps({'status': 'initialized'})  # JSON serialize details
    )
    
    db.session.add_all([admin_role, operator_role, viewer_role, admin_perm, read_perm, audit])
    db.session.commit()

