"""
LDAP/FreeIPA authentication for FleetOps.
"""

import logging
from typing import Optional, Tuple
import ldap
from ldap.modlist import addModlist

from models import db, User, Role
from config import get_config

logger = logging.getLogger(__name__)


class LDAPAuth:
    """LDAP/FreeIPA authentication handler."""

    def __init__(self):
        """Initialize LDAP handler."""
        self.config = get_config().get_ldap_config()
        self.conn = None

    def connect(self) -> bool:
        """
        Connect to LDAP server.

        Returns:
            True if successful, False otherwise
        """
        if not self.config['enabled']:
            logger.warning("LDAP is not enabled in configuration")
            return False

        try:
            uri = f"ldap://{self.config['server']}:{self.config['port']}"
            self.conn = ldap.initialize(uri)
            self.conn.set_option(ldap.OPT_REFERRALS, 0)

            # Enable TLS if configured
            if self.config['use_tls']:
                self.conn.start_tls_s()

            logger.info(f"Connected to LDAP server: {uri}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to LDAP server: {e}")
            return False

    def authenticate_user(self, username: str, password: str) -> Tuple[Optional[User], str]:
        """
        Authenticate user against LDAP.

        Args:
            username: Username
            password: Password

        Returns:
            Tuple of (User object or None, message)
        """
        if not self.connect():
            return None, "LDAP server connection failed"

        try:
            # Build user DN from template
            user_dn = self.config['user_dn_template'].format(username=username)

            # Attempt to bind with user credentials
            test_conn = ldap.initialize(f"ldap://{self.config['server']}:{self.config['port']}")
            if self.config['use_tls']:
                test_conn.start_tls_s()

            test_conn.simple_bind_s(user_dn, password)
            logger.info(f"LDAP authentication successful for: {username}")

            # Get or create user in local database
            user = self._sync_user_from_ldap(username, user_dn)
            if user:
                return user, "LDAP authentication successful"
            else:
                return None, "Failed to create local user from LDAP data"

        except ldap.INVALID_CREDENTIALS:
            logger.warning(f"LDAP authentication failed for {username}: Invalid credentials")
            return None, "Invalid credentials"

        except Exception as e:
            logger.error(f"LDAP authentication error: {e}")
            return None, f"LDAP authentication failed: {e}"

        finally:
            try:
                self.conn.unbind_s()
            except:
                pass

    def _sync_user_from_ldap(self, username: str, user_dn: str) -> Optional[User]:
        """
        Sync user from LDAP to local database.

        Args:
            username: Username
            user_dn: User's DN in LDAP

        Returns:
            User object or None
        """
        try:
            # Check if user already exists
            user = User.query.filter_by(username=username, auth_method='ldap').first()

            if not user:
                # Fetch user details from LDAP
                if not self.connect():
                    return None

                search_result = self.conn.search_s(user_dn, ldap.SCOPE_BASE)

                if not search_result:
                    logger.warning(f"User {username} not found in LDAP")
                    return None

                dn, attrs = search_result[0]
                email = attrs.get('mail', [b'unknown@example.com'])[0].decode('utf-8')

                # Create new user
                user = User(
                    username=username,
                    email=email,
                    auth_method='ldap'
                )
                db.session.add(user)

            # Get user groups and assign roles
            self._sync_user_roles(username)

            db.session.commit()
            logger.info(f"Synced LDAP user: {username}")
            return user

        except Exception as e:
            logger.error(f"Failed to sync user from LDAP: {e}")
            db.session.rollback()
            return None

    def _sync_user_roles(self, username: str) -> None:
        """
        Sync user roles based on LDAP group membership.

        Args:
            username: Username
        """
        try:
            user = User.query.filter_by(username=username).first()
            if not user:
                return

            if not self.connect():
                return

            # Get user's groups from LDAP
            user_groups = self._get_user_groups(username)

            # Map LDAP groups to roles
            group_to_role = {
                'mac_admins': 'admin',
                'mac_operators': 'operator',
                'mac_viewers': 'viewer',
            }

            # Clear existing roles
            user.roles.clear()

            # Assign roles based on group membership
            for group_name, role_name in group_to_role.items():
                if group_name in user_groups:
                    role = Role.query.filter_by(name=role_name).first()
                    if role:
                        user.roles.append(role)
                        logger.debug(f"Assigned role {role_name} to user {username}")

            # If no roles assigned, assign viewer role
            if not user.roles:
                viewer_role = Role.query.filter_by(name='viewer').first()
                if viewer_role:
                    user.roles.append(viewer_role)

            db.session.commit()

        except Exception as e:
            logger.error(f"Failed to sync user roles: {e}")
            db.session.rollback()

        finally:
            try:
                if self.conn:
                    self.conn.unbind_s()
            except:
                pass

    def _get_user_groups(self, username: str) -> list:
        """
        Get list of groups a user belongs to.

        Args:
            username: Username

        Returns:
            List of group names
        """
        groups = []
        try:
            if not self.conn:
                if not self.connect():
                    return groups

            # Search for groups that have this user as a member
            search_filter = f"(member=uid={username},cn=users,cn=accounts,{self.config['base_dn']})"
            result = self.conn.search_s(
                self.config['base_dn'],
                ldap.SCOPE_SUBTREE,
                search_filter,
                ['cn']
            )

            for dn, attrs in result:
                if attrs.get('cn'):
                    group_name = attrs['cn'][0].decode('utf-8')
                    groups.append(group_name)

        except Exception as e:
            logger.warning(f"Failed to get user groups: {e}")

        return groups

    def test_connection(self) -> Tuple[bool, str]:
        """
        Test LDAP connection.

        Returns:
            Tuple of (success, message)
        """
        if not self.connect():
            return False, "Failed to connect to LDAP server"

        try:
            # Try anonymous bind to test connection
            self.conn.simple_bind_s("", "")
            logger.info("LDAP connection test successful")
            return True, "LDAP connection successful"

        except Exception as e:
            logger.error(f"LDAP connection test failed: {e}")
            return False, f"LDAP test failed: {e}"

        finally:
            try:
                self.conn.unbind_s()
            except:
                pass


def authenticate_ldap(username: str, password: str) -> Tuple[Optional[User], str]:
    """
    Authenticate user with LDAP.

    Args:
        username: Username
        password: Password

    Returns:
        Tuple of (User object or None, message)
    """
    ldap_auth = LDAPAuth()
    return ldap_auth.authenticate_user(username, password)


def test_ldap_connection() -> Tuple[bool, str]:
    """
    Test LDAP connection.

    Returns:
        Tuple of (success, message)
    """
    ldap_auth = LDAPAuth()
    return ldap_auth.test_connection()
