"""
SQLAlchemy models for FleetOps.
Includes User, Role, Permission, Secret, and other domain models.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# Association tables for many-to-many relationships

user_roles = db.Table(
    'user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
)

role_permissions = db.Table(
    'role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permission.id'), primary_key=True)
)

tool_access = db.Table(
    'tool_access',
    db.Column('tool_name', db.String(64), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
)


class User(db.Model):
    """User account model."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    auth_method = db.Column(db.String(20), nullable=False, default='local')  # local or ldap
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # Relationships
    roles = db.relationship('Role', secondary=user_roles, backref=db.backref('users', lazy='dynamic'))

    def set_password(self, password: str) -> None:
        """Set password hash for user."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check if provided password matches hash."""
        return check_password_hash(self.password_hash, password)

    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role."""
        return any(role.name == role_name for role in self.roles)

    def has_permission(self, resource: str, action: str) -> bool:
        """Check if user has a specific permission."""
        for role in self.roles:
            if role.has_permission(resource, action):
                return True
        return False

    def get_permissions(self) -> list:
        """Get all permissions for this user."""
        permissions = set()
        for role in self.roles:
            for perm in role.permissions:
                permissions.add(f"{perm.resource}:{perm.action}")
        return list(permissions)

    def record_login(self) -> None:
        """Update last login timestamp."""
        self.last_login = datetime.utcnow()
        db.session.commit()

    def __repr__(self) -> str:
        return f'<User {self.username}>'


class Role(db.Model):
    """Role model for RBAC."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    permissions = db.relationship('Permission', secondary=role_permissions, backref=db.backref('roles', lazy='dynamic'))

    def has_permission(self, resource: str, action: str) -> bool:
        """Check if role has a specific permission."""
        return any(p.resource == resource and p.action == action for p in self.permissions)

    def add_permission(self, resource: str, action: str) -> None:
        """Add a permission to this role."""
        perm = Permission.query.filter_by(resource=resource, action=action).first()
        if not perm:
            perm = Permission(resource=resource, action=action)
            db.session.add(perm)
        if perm not in self.permissions:
            self.permissions.append(perm)

    def __repr__(self) -> str:
        return f'<Role {self.name}>'


class Permission(db.Model):
    """Permission model."""

    id = db.Column(db.Integer, primary_key=True)
    resource = db.Column(db.String(64), nullable=False)
    action = db.Column(db.String(64), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('resource', 'action', name='uq_resource_action'),)

    def __repr__(self) -> str:
        return f'<Permission {self.resource}:{self.action}>'


class Secret(db.Model):
    """Encrypted secrets vault."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False, index=True)
    value_encrypted = db.Column(db.LargeBinary, nullable=False)
    secret_type = db.Column(db.String(32), nullable=False, default='password')  # password, api_key, token, ssh_key
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # Relationships
    created_by = db.relationship('User', backref=db.backref('created_secrets', lazy='dynamic'))

    def __repr__(self) -> str:
        return f'<Secret {self.name}>'


class AuditLog(db.Model):
    """Audit trail for security events."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    resource = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 or IPv6
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = db.relationship('User', backref=db.backref('audit_logs', lazy='dynamic'))

    def __repr__(self) -> str:
        return f'<AuditLog {self.action} on {self.resource}>'


def init_db(app) -> None:
    """Initialize database with Flask app."""
    db.init_app(app)
    with app.app_context():
        db.create_all()


def create_default_roles(app) -> None:
    """Create default roles if they don't exist."""
    with app.app_context():
        # Check if roles already exist
        if Role.query.first() is not None:
            return

        # Create default roles
        admin_role = Role(name='admin', description='Administrator with full access')
        operator_role = Role(name='operator', description='Can execute playbooks and manage resources')
        viewer_role = Role(name='viewer', description='Read-only access to view resources')

        # Add permissions to roles
        admin_role.add_permission('ansible', 'view_playbooks')
        admin_role.add_permission('ansible', 'execute_playbook')
        admin_role.add_permission('ansible', 'view_inventory')
        admin_role.add_permission('ansible', 'edit_inventory')
        admin_role.add_permission('ansible', 'view_ssh')
        admin_role.add_permission('ansible', 'access_terminal')
        admin_role.add_permission('admin', 'manage_users')
        admin_role.add_permission('admin', 'manage_roles')
        admin_role.add_permission('admin', 'manage_secrets')
        admin_role.add_permission('admin', 'view_audit_logs')

        operator_role.add_permission('ansible', 'view_playbooks')
        operator_role.add_permission('ansible', 'execute_playbook')
        operator_role.add_permission('ansible', 'view_inventory')
        operator_role.add_permission('ansible', 'view_ssh')
        operator_role.add_permission('ansible', 'access_terminal')

        viewer_role.add_permission('ansible', 'view_playbooks')
        viewer_role.add_permission('ansible', 'view_inventory')

        db.session.add(admin_role)
        db.session.add(operator_role)
        db.session.add(viewer_role)
        db.session.commit()
