"""
Secrets API routes for FleetOps.
Provides endpoints for managing encrypted secrets.
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from models import db, Secret
from vault import get_vault
from admin_routes import require_permission

secrets_bp = Blueprint('secrets', __name__, url_prefix='/admin/secrets')


@secrets_bp.route('', methods=['GET'])
@require_permission('admin', 'manage_secrets')
def list_secrets():
    """List all secrets (without values)."""
    secrets = Secret.query.all()
    return jsonify([{
        "id": s.id,
        "name": s.name,
        "secret_type": s.secret_type,
        "description": s.description,
        "created_at": s.created_at.isoformat(),
        "created_by": s.created_by.username if s.created_by else "system"
    } for s in secrets]), 200


@secrets_bp.route('', methods=['POST'])
@require_permission('admin', 'manage_secrets')
def create_secret():
    """Create a new secret."""
    data = request.get_json()
    name = data.get('name', '').strip()
    value = data.get('value', '')
    secret_type = data.get('secret_type', 'password')
    description = data.get('description', '').strip()

    if not name or not value:
        return jsonify({"error": "Name and value are required"}), 400

    # Check if secret already exists
    if Secret.query.filter_by(name=name).first():
        return jsonify({"error": f"Secret '{name}' already exists"}), 400

    try:
        vault = get_vault()
        encrypted_value = vault.encrypt(value)

        secret = Secret(
            name=name,
            value_encrypted=encrypted_value,
            secret_type=secret_type,
            description=description,
            created_by_id=current_user.id
        )

        db.session.add(secret)
        db.session.commit()

        return jsonify({
            "id": secret.id,
            "name": secret.name,
            "secret_type": secret.secret_type,
            "description": secret.description
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to create secret: {e}"}), 500


@secrets_bp.route('/<int:secret_id>', methods=['GET'])
@require_permission('admin', 'manage_secrets')
def get_secret(secret_id: int):
    """Get secret value (requires permission)."""
    secret = Secret.query.get(secret_id)
    if not secret:
        return jsonify({"error": "Secret not found"}), 404

    try:
        vault = get_vault()
        value = vault.decrypt(secret.value_encrypted)

        return jsonify({
            "id": secret.id,
            "name": secret.name,
            "value": value,
            "secret_type": secret.secret_type,
            "description": secret.description
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to decrypt secret: {e}"}), 500


@secrets_bp.route('/<int:secret_id>', methods=['PUT'])
@require_permission('admin', 'manage_secrets')
def update_secret(secret_id: int):
    """Update a secret."""
    secret = Secret.query.get(secret_id)
    if not secret:
        return jsonify({"error": "Secret not found"}), 404

    data = request.get_json()

    try:
        vault = get_vault()

        if 'value' in data:
            secret.value_encrypted = vault.encrypt(data['value'])

        if 'secret_type' in data:
            secret.secret_type = data['secret_type']

        if 'description' in data:
            secret.description = data['description']

        db.session.commit()

        return jsonify({
            "id": secret.id,
            "name": secret.name,
            "secret_type": secret.secret_type,
            "description": secret.description,
            "updated_at": secret.updated_at.isoformat()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update secret: {e}"}), 500


@secrets_bp.route('/<int:secret_id>', methods=['DELETE'])
@require_permission('admin', 'manage_secrets')
def delete_secret(secret_id: int):
    """Delete a secret."""
    secret = Secret.query.get(secret_id)
    if not secret:
        return jsonify({"error": "Secret not found"}), 404

    try:
        db.session.delete(secret)
        db.session.commit()
        return jsonify({"message": "Secret deleted successfully"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete secret: {e}"}), 500


@secrets_bp.route('/by-name/<name>', methods=['GET'])
@login_required
def get_secret_by_name(name: str):
    """Get secret by name (for use in playbooks)."""
    secret = Secret.query.filter_by(name=name).first()
    if not secret:
        return jsonify({"error": "Secret not found"}), 404

    try:
        vault = get_vault()
        value = vault.decrypt(secret.value_encrypted)
        return jsonify({"value": value}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to decrypt secret: {e}"}), 500


def register_secrets_routes(app):
    """Register secrets routes with Flask app."""
    app.register_blueprint(secrets_bp)
