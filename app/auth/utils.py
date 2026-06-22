import hashlib
import secrets

import bcrypt


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    bcrypt has a 72-byte input limit, so we truncate the UTF-8 encoded
    password to 72 bytes before hashing.
    """
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode()[:72], hashed_password.encode())


def generate_api_token() -> tuple[str, str, str]:
    """Generate a permanent API token.

    Returns:
        (raw_token, token_hash, token_prefix)

    The raw token is ``user_`` + 43 URL-safe base64 chars (32 bytes / 256 bits
    of entropy).  Only the SHA-256 hex digest is stored in the database.
    """
    raw = "user_" + secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    token_prefix = raw[:8]
    return raw, token_hash, token_prefix


def hash_token(raw_token: str) -> str:
    """Hash a raw token string for database lookup."""
    return hashlib.sha256(raw_token.encode()).hexdigest()
