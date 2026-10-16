"""Versioned scrypt password hashes; credentials are never command-line arguments."""

import hashlib
import re
import secrets


def username(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{3,64}", value):
        raise ValueError("LOGIN_USERNAME_INVALID")
    return value.lower()


def derive(password, salt):
    # OWASP scrypt minimum: N=2^17, r=8, p=1. Explicit OpenSSL memory limit.
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**17, r=8,
                          p=1, dklen=32, maxmem=256 * 1024**2)


def hash_password(password):
    if not isinstance(password, str) or not 10 <= len(password) <= 256:
        raise ValueError("PASSWORD_LENGTH_10_TO_256_REQUIRED")
    salt = secrets.token_bytes(16)
    return "scrypt-v1$" + salt.hex() + "$" + derive(password, salt).hex()


def verify_password(password, encoded):
    # Unknown users perform the same expensive operation as an existing user.
    if not encoded:
        encoded = "scrypt-v1$" + "00" * 16 + "$" + "00" * 32
    version, salt, expected = encoded.split("$")
    if version != "scrypt-v1":
        return False
    actual = derive(password, bytes.fromhex(salt))
    return secrets.compare_digest(actual, bytes.fromhex(expected))
