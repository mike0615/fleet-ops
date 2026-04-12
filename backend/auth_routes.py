"""
Authentication routes for Maytag Admin Console.
Provides login/logout endpoints and session management.
"""

from flask import Blueprint, request, jsonify, session, redirect, url_for
from flask_login import login_user, logout_user, login_required, current_user

from models import db, User
from auth import authenticate_local, log_auth_event

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login endpoint - authenticate user."""
    if request.method == 'GET':
        # Return login page (will be served by frontend)
        return jsonify({"message": "Use POST to login"}), 405

    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            log_auth_event('login_failed', 'missing_credentials')
            return jsonify({"error": "Username and password required"}), 400

        user, msg = authenticate_local(username, password)

        if not user:
            return jsonify({"error": msg}), 401

        # Create authenticated wrapper
        from auth import AuthenticatedUser
        auth_user = AuthenticatedUser(user)
        login_user(auth_user, remember=data.get('remember_me', False))

        return jsonify({
            "message": "Login successful",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "roles": [r.name for r in user.roles],
                "permissions": user.get_permissions()
            }
        }), 200


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """Logout endpoint - clear session."""
    username = current_user.username
    logout_user()
    log_auth_event('logout', f'user: {username}')
    return jsonify({"message": "Logged out successfully"}), 200


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current user info."""
    user = current_user.user
    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "roles": [r.name for r in user.roles],
        "permissions": user.get_permissions(),
        "last_login": user.last_login.isoformat() if user.last_login else None
    }), 200


@auth_bp.route('/permissions', methods=['GET'])
@login_required
def get_permissions():
    """Get current user permissions."""
    return jsonify({
        "permissions": current_user.get_permissions()
    }), 200


def register_auth_routes(app):
    """Register authentication routes with Flask app."""
    app.register_blueprint(auth_bp)
