"""
Admin routes for Maytag Admin Console.
Provides endpoints for user/role/permission management.
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from models import db, User, Role, Permission, AuditLog
from auth import create_user, disable_user, enable_user, reset_password

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def require_permission(resource: str, action: str):
    """Decorator to require specific permission."""
    from functools import wraps

    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.has_permission(resource, action):
                return jsonify({"error": "Permission denied"}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ─── User Management ──────────────────────────────────────────────────────────

@admin_bp.route('/users', methods=['GET'])
@require_permission('admin', 'manage_users')
def list_users():
    """List all users."""
    users = User.query.all()
    return jsonify([{
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "roles": [r.name for r in u.roles],
        "enabled": u.enabled,
        "auth_method": u.auth_method,
        "created_at": u.created_at.isoformat(),
        "last_login": u.last_login.isoformat() if u.last_login else None
    } for u in users]), 200


@admin_bp.route('/users', methods=['POST'])
@require_permission('admin', 'manage_users')
def create_new_user():
    """Create a new user."""
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    roles = data.get('roles', [])

    if not username or not email or not password:
        return jsonify({"error": "Username, email, and password required"}), 400

    user, msg = create_user(username, email, password, auth_method='local', roles=roles)

    if not user:
        return jsonify({"error": msg}), 400

    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "roles": [r.name for r in user.roles]
    }), 201


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@require_permission('admin', 'manage_users')
def get_user(user_id: int):
    """Get user details."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "roles": [r.name for r in user.roles],
        "enabled": user.enabled,
        "auth_method": user.auth_method,
        "created_at": user.created_at.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None
    }), 200


@admin_bp.route('/users/<int:user_id>/roles', methods=['PUT'])
@require_permission('admin', 'manage_users')
def update_user_roles(user_id: int):
    """Update user roles."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    role_names = data.get('roles', [])

    # Clear existing roles
    user.roles.clear()

    # Add new roles
    for role_name in role_names:
        role = Role.query.filter_by(name=role_name).first()
        if role:
            user.roles.append(role)

    db.session.commit()

    return jsonify({
        "username": user.username,
        "roles": [r.name for r in user.roles]
    }), 200


@admin_bp.route('/users/<int:user_id>/disable', methods=['POST'])
@require_permission('admin', 'manage_users')
def disable_user_endpoint(user_id: int):
    """Disable a user."""
    success, msg = disable_user(user_id)
    if not success:
        return jsonify({"error": msg}), 400
    return jsonify({"message": msg}), 200


@admin_bp.route('/users/<int:user_id>/enable', methods=['POST'])
@require_permission('admin', 'manage_users')
def enable_user_endpoint(user_id: int):
    """Enable a user."""
    success, msg = enable_user(user_id)
    if not success:
        return jsonify({"error": msg}), 400
    return jsonify({"message": msg}), 200


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@require_permission('admin', 'manage_users')
def reset_user_password(user_id: int):
    """Reset user password."""
    data = request.get_json()
    password = data.get('password', '')

    if not password:
        return jsonify({"error": "Password required"}), 400

    success, msg = reset_password(user_id, password)
    if not success:
        return jsonify({"error": msg}), 400

    return jsonify({"message": msg}), 200


# ─── Role Management ──────────────────────────────────────────────────────────

@admin_bp.route('/roles', methods=['GET'])
@require_permission('admin', 'manage_roles')
def list_roles():
    """List all roles."""
    roles = Role.query.all()
    return jsonify([{
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "permissions": [f"{p.resource}:{p.action}" for p in r.permissions]
    } for r in roles]), 200


@admin_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@require_permission('admin', 'manage_roles')
def update_role_permissions(role_id: int):
    """Update role permissions."""
    role = Role.query.get(role_id)
    if not role:
        return jsonify({"error": "Role not found"}), 404

    data = request.get_json()
    permissions = data.get('permissions', [])

    # Clear existing permissions
    role.permissions.clear()

    # Add new permissions
    for perm_str in permissions:
        parts = perm_str.split(':')
        if len(parts) == 2:
            resource, action = parts
            perm = Permission.query.filter_by(resource=resource, action=action).first()
            if perm:
                role.permissions.append(perm)

    db.session.commit()

    return jsonify({
        "name": role.name,
        "permissions": [f"{p.resource}:{p.action}" for p in role.permissions]
    }), 200


# ─── Audit Logs ────────────────────────────────────────────────────────────

@admin_bp.route('/audit-logs', methods=['GET'])
@require_permission('admin', 'view_audit_logs')
def get_audit_logs():
    """Get audit logs."""
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset).all()
    total = AuditLog.query.count()

    return jsonify({
        "total": total,
        "logs": [{
            "id": l.id,
            "user": l.user.username if l.user else "system",
            "action": l.action,
            "resource": l.resource,
            "details": l.details,
            "ip_address": l.ip_address,
            "timestamp": l.timestamp.isoformat()
        } for l in logs]
    }), 200


def register_admin_routes(app):
    """Register admin routes with Flask app."""
    app.register_blueprint(admin_bp)
