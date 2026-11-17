"""Owner-scoped encrypted SSH settings. No endpoint returns stored passwords."""
import json
from functools import wraps
from urllib.parse import urlsplit
from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from models import db, SSHCredential
from vault import get_vault

bp = Blueprint('ssh_credentials', __name__, url_prefix='/api/ssh-credentials')

def authorized(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(error='Authentication required'), 401
        if not current_user.has_permission('ansible', 'access_terminal'):
            return jsonify(error='SSH permission required'), 403
        origin = request.headers.get('Origin')
        if request.method != 'GET' and origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in ('http', 'https') or parsed.netloc != request.host:
                return jsonify(error='Same-origin request required'), 403
        return func(*args, **kwargs)
    return wrapped

def resolve_credential(credential_id, owner_id):
    row = SSHCredential.query.filter_by(id=int(credential_id), owner_id=owner_id).first()
    if row is None:
        raise ValueError('Credential unavailable')
    return json.loads(get_vault().decrypt(row.value_encrypted))

@bp.route('', methods=['GET'])
@authorized
def list_credentials():
    result = []
    try:
        for row in SSHCredential.query.filter_by(owner_id=current_user.id).order_by(SSHCredential.label):
            settings = resolve_credential(row.id, current_user.id)
            result.append(dict(id=row.id, label=row.label, host=settings['host'], port=settings['port'], username=settings['username']))
        return jsonify(result)
    except Exception:
        return jsonify(error='Vault unavailable; verify the persistent encryption key'), 503

@bp.route('', methods=['POST'])
@authorized
def save_credential():
    data = request.get_json(silent=True) or {}
    try:
        label, host, username = (str(data.get(k, '')).strip() for k in ('label', 'host', 'username'))
        password = data.get('password')
        port = int(data.get('port', 22))
        if not label or len(label) > 128 or not host or len(host) > 255 or not username or len(username) > 255 or not isinstance(password, str) or not password or len(password) > 16384 or not 1 <= port <= 65535:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify(error='A name, host, username, password and valid port are required'), 400
    try:
        payload = json.dumps(dict(host=host, port=port, username=username, password=password))
        row = SSHCredential(owner_id=current_user.id, label=label, value_encrypted=get_vault().encrypt(payload))
        db.session.add(row)
        db.session.commit()
        return jsonify(id=row.id, label=row.label), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='You already have saved credentials with that name'), 409
    except Exception:
        db.session.rollback()
        return jsonify(error='Unable to encrypt and save credentials'), 503

@bp.route('/<int:credential_id>', methods=['DELETE'])
@authorized
def delete_credential(credential_id):
    row = SSHCredential.query.filter_by(id=credential_id, owner_id=current_user.id).first()
    if row is None:
        return jsonify(error='Credential unavailable'), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify(success=True)

def register_ssh_credentials(app):
    app.register_blueprint(bp)
