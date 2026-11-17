"""
Authentication module for FleetOps.
Handles local and LDAP user authentication.
"""

import logging
import re
from typing import Optional, Tuple
from datetime import datetime

from flask import request
from flask_login import LoginManager, UserMixin

from models import db, User, AuditLog, Role
from config import get_config

logger = logging.getLogger(__name__)

# Password validation patterns
PASSWORD_MIN_LENGTH = 8
PASSWORD_PATTERN = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[a-zA-Z\d@$!%*?&]{8,}$')


class AuthenticatedUser(UserMixin):
    """User wrapper for Flask-Login."""

    def __init__(self, user: User):
        self.user = user

    def get_id(self) -> str:
        return str(self.user.id)

    @property
    def id(self):
        return self.user.id

    @property
    def username(self):
        return self.user.username

    @property
    def email(self):
        return self.user.email

    def has_permission(self, resource: str, action: str) -> bool:
        """Check if user has permission."""
        return self.user.has_permission(resource, action)

    def get_permissions(self) -> list:
        """Get all user permissions."""
        return self.user.get_permissions()


def init_login_manager(app, login_manager: LoginManager) -> None:
    """Initialize Flask-Login with FleetOps."""
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'

    @login_manager.user_loader
    def load_user(user_id: str) -> Optional[AuthenticatedUser]:
        """Load user by ID."""
        try:
            user = User.query.get(int(user_id))
            if user and user.enabled:
                return AuthenticatedUser(user)
        except Exception as e:
            logger.error(f"Error loading user {user_id}: {e}")
        return None


def validate_password(password: str) -> Tuple[bool, str]:
    """
    Validate password strength.

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, message)
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {PASSWORD_MIN_LENGTH} characters"

    if not PASSWORD_PATTERN.match(password):
        return False, "Password must contain uppercase, lowercase, and digits"

    return True, "Password is valid"


def create_user(
    username: str,
    email: str,
    password: str,
    auth_method: str = 'local',
    roles: list = None
) -> Tuple[Optional[User], str]:
    """
    Create a new local user.

    Args:
        username: Username
        email: Email address
        password: Password
        auth_method: Auth method (local or ldap)
        roles: List of role names to assign

    Returns:
        Tuple of (User object or None, message)
    """
    # Validate password
    if auth_method == 'local':
        valid, msg = validate_password(password)
        if not valid:
            return None, msg

    # Check if user already exists
    if User.query.filter_by(username=username).first():
        return None, f"User '{username}' already exists"

    if User.query.filter_by(email=email).first():
        return None, f"Email '{email}' already in use"

    try:
        user = User(username=username, email=email, auth_method=auth_method)
        if auth_method == 'local':
            user.set_password(password)

        # Assign roles
        if roles:
            for role_name in roles:
                role = Role.query.filter_by(name=role_name).first()
                if role:
                    user.roles.append(role)

        db.session.add(user)
        db.session.commit()

        logger.info(f"Created user: {username} ({auth_method})")
        return user, "User created successfully"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create user: {e}")
        return None, f"Failed to create user: {e}"


def authenticate_local(username: str, password: str) -> Tuple[Optional[User], str]:
    """
    Authenticate user with local credentials.

    Args:
        username: Username
        password: Password

    Returns:
        Tuple of (User object or None, message)
    """
    user = User.query.filter_by(username=username, auth_method='local').first()

    if not user:
        log_auth_event('login_failed', f'user_not_found: {username}')
        return None, "Invalid username or password"

    if not user.enabled:
        log_auth_event('login_failed', f'user_disabled: {username}')
        return None, "User account is disabled"

    if not user.check_password(password):
        log_auth_event('login_failed', f'invalid_password: {username}')
        return None, "Invalid username or password"

    user.record_login()
    log_auth_event('login_success', f'user: {username}')
    logger.info(f"User authenticated: {username}")

    return user, "Authentication successful"


def authenticate_ldap(username: str, password: str) -> Tuple[Optional[User], str]:
    """
    Authenticate user with LDAP.

    Args:
        username: Username
        password: Password

    Returns:
        Tuple of (User object or None, message)
    """
    try:
        from ldap_auth import LDAPAuth
        ldap_auth = LDAPAuth()
        user, msg = ldap_auth.authenticate_user(username, password)
        
        if user:
            if not user.enabled:
                log_auth_event('login_failed', f'user_disabled: {username}')
                return None, "User account is disabled"
            
            user.record_login()
            log_auth_event('login_success', f'ldap_user: {username}')
            logger.info(f"LDAP user authenticated: {username}")
        else:
            log_auth_event('login_failed', f'ldap_auth_failed: {username}')
            logger.warning(f"LDAP authentication failed for {username}: {msg}")
        
        return user, msg
    
    except Exception as e:
        logger.error(f"LDAP authentication error: {e}")
        log_auth_event('login_failed', f'ldap_error: {str(e)}')
        return None, f"LDAP authentication error: {e}"


def authenticate(
    username: str, 
    password: str, 
    auth_method: str = 'auto'
) -> Tuple[Optional[User], str]:
    """
    Authenticate user with specified or auto-detected method.

    Args:
        username: Username
        password: Password
        auth_method: 'local', 'ldap', or 'auto' to try both

    Returns:
        Tuple of (User object or None, message)
    """
    if auth_method == 'local':
        return authenticate_local(username, password)
    
    elif auth_method == 'ldap':
        return authenticate_ldap(username, password)
    
    elif auth_method == 'auto':
        # Try LDAP first if enabled, then fall back to local
        config = get_config()
        if config.get('LDAP_ENABLED'):
            user, msg = authenticate_ldap(username, password)
            if user:
                return user, msg
            # Fall through to local auth if LDAP fails
            logger.debug(f"LDAP auth failed for {username}, trying local auth")
        
        # Try local authentication
        return authenticate_local(username, password)
    
    else:
        return None, f"Unknown authentication method: {auth_method}"


def log_auth_event(action: str, details: str = "") -> None:
    """Log authentication event to audit trail."""
    try:
        from flask_login import current_user

        user_id = current_user.id if current_user and current_user.is_authenticated else None
        ip_address = request.remote_addr if request else None

        audit = AuditLog(
            user_id=user_id,
            action=action,
            resource='authentication',
            details=details,
            ip_address=ip_address
        )
        db.session.add(audit)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to log auth event: {e}")


def disable_user(user_id: int) -> Tuple[bool, str]:
    """
    Disable a user account.

    Args:
        user_id: User ID

    Returns:
        Tuple of (success, message)
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"

        user.enabled = False
        db.session.commit()
        logger.info(f"Disabled user: {user.username}")
        return True, "User disabled successfully"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to disable user: {e}")
        return False, f"Failed to disable user: {e}"


def enable_user(user_id: int) -> Tuple[bool, str]:
    """
    Enable a user account.

    Args:
        user_id: User ID

    Returns:
        Tuple of (success, message)
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"

        user.enabled = True
        db.session.commit()
        logger.info(f"Enabled user: {user.username}")
        return True, "User enabled successfully"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to enable user: {e}")
        return False, f"Failed to enable user: {e}"


def reset_password(user_id: int, new_password: str) -> Tuple[bool, str]:
    """
    Reset user password (admin function).

    Args:
        user_id: User ID
        new_password: New password

    Returns:
        Tuple of (success, message)
    """
    valid, msg = validate_password(new_password)
    if not valid:
        return False, msg

    try:
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"

        user.set_password(new_password)
        db.session.commit()
        logger.info(f"Reset password for user: {user.username}")
        return True, "Password reset successfully"

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to reset password: {e}")
        return False, f"Failed to reset password: {e}"
