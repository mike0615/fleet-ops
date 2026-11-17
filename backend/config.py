"""
Configuration management for FleetOps.
Handles auth configuration, tool settings, and system configuration.
"""

import os
import logging
from typing import Dict, Any, Optional
from configparser import ConfigParser
from pathlib import Path

logger = logging.getLogger(__name__)


class Config:
    """Central configuration manager."""

    # Default values
    DEFAULTS = {
        'DATABASE_URL': os.environ.get('FLEETOPS_DATABASE_URL', 'sqlite:///' + os.environ.get('FLEETOPS_DATA_DIR', '/var/lib/fleetops') + '/fleetops.db'),
        'SECRET_KEY': os.urandom(32).hex(),
        'SESSION_TIMEOUT': 30 * 60,  # 30 minutes in seconds
        'LDAP_ENABLED': False,
        'LDAP_SERVER': 'ldap.example.com',
        'LDAP_PORT': 389,
        'LDAP_USE_TLS': True,
        'LDAP_BASE_DN': 'dc=example,dc=com',
        'LDAP_USER_DN_TEMPLATE': 'uid={username},cn=users,cn=accounts,dc=example,dc=com',
        'LDAP_GROUP_DN_TEMPLATE': 'cn={groupname},cn=groups,cn=accounts,dc=example,dc=com',
        'LDAP_SEARCH_DN': '',
        'LDAP_SEARCH_PASSWORD': '',
    }

    def __init__(self, config_file: str = None):
        """
        Initialize configuration.

        Args:
            config_file: Path to config file (optional, defaults to /etc/fleetops/mac.conf)
        """
        self.config = self.DEFAULTS.copy()
        self.config_file = config_file or os.environ.get('FLEETOPS_CONFIG', '/etc/fleetops/fleetops.conf')

        # Load from environment variables first
        self._load_from_env()

        # Load from config file if it exists
        if Path(self.config_file).exists():
            self._load_from_file(self.config_file)

        key_file = Path(os.environ.get('FLEETOPS_KEY_FILE', '/etc/fleetops/session.key'))
        if key_file.exists() and 'FLEETOPS_SECRET_KEY' not in os.environ:
            self.config['SECRET_KEY'] = key_file.read_text().strip()
        logger.info("Configuration loaded")

    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        for key in self.DEFAULTS.keys():
            env_key = f"FLEETOPS_{key}"
            if env_key in os.environ:
                value = os.environ[env_key]
                # Convert string boolean values
                if value.lower() in ('true', 'yes', '1'):
                    self.config[key] = True
                elif value.lower() in ('false', 'no', '0'):
                    self.config[key] = False
                else:
                    self.config[key] = value
                logger.debug(f"Loaded from env: {key}")

    def _load_from_file(self, filepath: str) -> None:
        """Load configuration from file."""
        try:
            parser = ConfigParser()
            parser.read(filepath)

            # Read [auth] section
            if parser.has_section('auth'):
                for key, value in parser.items('auth'):
                    config_key = key.upper()
                    if config_key in self.DEFAULTS:
                        # Convert string boolean values
                        if value.lower() in ('true', 'yes', '1'):
                            self.config[config_key] = True
                        elif value.lower() in ('false', 'no', '0'):
                            self.config[config_key] = False
                        else:
                            self.config[config_key] = value
                        logger.debug(f"Loaded from file: {config_key}")

            # Read [database] section
            if parser.has_section('database'):
                if parser.has_option('database', 'url'):
                    self.config['DATABASE_URL'] = parser.get('database', 'url')

            # Read [ldap] section
            if parser.has_section('ldap'):
                for key, value in parser.items('ldap'):
                    config_key = 'LDAP_' + key.upper()
                    if config_key in self.DEFAULTS:
                        if value.lower() in ('true', 'yes', '1'):
                            self.config[config_key] = True
                        elif value.lower() in ('false', 'no', '0'):
                            self.config[config_key] = False
                        else:
                            self.config[config_key] = value

            logger.info(f"Configuration loaded from {filepath}")

        except Exception as e:
            logger.error(f"Failed to load config from {filepath}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value.

        Args:
            key: Configuration key
            value: Value to set
        """
        self.config[key] = value
        logger.debug(f"Configuration set: {key} = {value}")

    def get_ldap_config(self) -> Dict[str, Any]:
        """Get LDAP configuration as dict."""
        return {
            'enabled': self.get('LDAP_ENABLED'),
            'server': self.get('LDAP_SERVER'),
            'port': int(self.get('LDAP_PORT', 389)),
            'use_tls': self.get('LDAP_USE_TLS'),
            'base_dn': self.get('LDAP_BASE_DN'),
            'user_dn_template': self.get('LDAP_USER_DN_TEMPLATE'),
            'group_dn_template': self.get('LDAP_GROUP_DN_TEMPLATE'),
            'search_dn': self.get('LDAP_SEARCH_DN'),
            'search_password': self.get('LDAP_SEARCH_PASSWORD'),
        }

    def get_database_url(self) -> str:
        """Get database URL."""
        return self.get('DATABASE_URL')

    def get_secret_key(self) -> str:
        """Get Flask secret key."""
        return self.get('SECRET_KEY')

    def get_session_timeout(self) -> int:
        """Get session timeout in seconds."""
        return int(self.get('SESSION_TIMEOUT', 30 * 60))

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary (excluding sensitive values)."""
        safe_config = {}
        for key, value in self.config.items():
            # Don't expose sensitive values
            if 'PASSWORD' in key or 'SECRET' in key or 'KEY' in key:
                safe_config[key] = '***REDACTED***'
            else:
                safe_config[key] = value
        return safe_config


# Global configuration instance
config: Optional[Config] = None


def init_config(config_file: str = None) -> Config:
    """Initialize global configuration."""
    global config
    config = Config(config_file)
    return config


def get_config() -> Config:
    """Get global configuration instance."""
    global config
    if config is None:
        config = Config()
    return config
