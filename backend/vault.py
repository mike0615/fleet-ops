"""
Secrets vault for Maytag Admin Console.
Provides encryption/decryption of sensitive data at rest.
"""

import os
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class SecretsVault:
    """Manages encryption and decryption of secrets."""

    def __init__(self, key: bytes = None):
        """
        Initialize the secrets vault.

        Args:
            key: Encryption key (bytes). If None, will be loaded from environment or generated.
        """
        if key is None:
            key_str = os.environ.get('MAC_SECRETS_KEY')
            if key_str:
                key = key_str.encode()
            else:
                # Generate a new key (should be persisted in production)
                key = Fernet.generate_key()
                logger.warning(
                    "No MAC_SECRETS_KEY found. Generated new key. "
                    "Store this in /etc/mac-ops/.secrets_key or MAC_SECRETS_KEY environment variable."
                )

        try:
            self.cipher = Fernet(key)
        except Exception as e:
            logger.error(f"Failed to initialize cipher: {e}")
            raise ValueError("Invalid encryption key provided")

    def encrypt(self, plaintext: str) -> bytes:
        """
        Encrypt plaintext secret.

        Args:
            plaintext: Secret to encrypt

        Returns:
            Encrypted bytes
        """
        try:
            if isinstance(plaintext, str):
                plaintext = plaintext.encode('utf-8')
            return self.cipher.encrypt(plaintext)
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def decrypt(self, ciphertext: bytes) -> str:
        """
        Decrypt ciphertext secret.

        Args:
            ciphertext: Encrypted bytes

        Returns:
            Decrypted plaintext string
        """
        try:
            plaintext = self.cipher.decrypt(ciphertext)
            return plaintext.decode('utf-8')
        except InvalidToken:
            logger.error("Decryption failed: Invalid token")
            raise ValueError("Failed to decrypt secret: invalid data")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise

    @staticmethod
    def generate_key() -> bytes:
        """
        Generate a new encryption key.

        Returns:
            New Fernet key as bytes
        """
        return Fernet.generate_key()

    @staticmethod
    def save_key_to_file(key: bytes, filepath: str, permissions: int = 0o600) -> None:
        """
        Save encryption key to file with restricted permissions.

        Args:
            key: Encryption key
            filepath: Path to save key file
            permissions: File permissions (default: 0o600 for owner read/write only)
        """
        try:
            # Create directory if needed
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # Write key
            with open(filepath, 'wb') as f:
                f.write(key)

            # Set restrictive permissions
            os.chmod(filepath, permissions)
            logger.info(f"Secrets key saved to {filepath} with permissions {oct(permissions)}")
        except Exception as e:
            logger.error(f"Failed to save secrets key: {e}")
            raise

    @staticmethod
    def load_key_from_file(filepath: str) -> bytes:
        """
        Load encryption key from file.

        Args:
            filepath: Path to key file

        Returns:
            Encryption key as bytes
        """
        try:
            with open(filepath, 'rb') as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Secrets key file not found: {filepath}")
        except Exception as e:
            logger.error(f"Failed to load secrets key: {e}")
            raise


# Global vault instance (initialized in app setup)
vault: Optional[SecretsVault] = None


def init_vault(app) -> None:
    """Initialize the global secrets vault."""
    global vault

    # Try to load key from file first
    key_file = '/etc/mac-ops/.secrets_key'
    key = None

    if os.path.exists(key_file):
        try:
            key = SecretsVault.load_key_from_file(key_file)
        except Exception as e:
            logger.error(f"Failed to load key from {key_file}: {e}")

    # Initialize vault
    vault = SecretsVault(key)

    # If key was generated, save it
    if key is None:
        try:
            SecretsVault.save_key_to_file(vault.cipher._signing_key + vault.cipher._encryption_key, key_file)
        except Exception as e:
            logger.warning(f"Could not save key file: {e}. Key will not persist across restarts.")


def get_vault() -> SecretsVault:
    """Get the global secrets vault instance."""
    global vault
    if vault is None:
        raise RuntimeError("Vault not initialized. Call init_vault(app) first.")
    return vault
