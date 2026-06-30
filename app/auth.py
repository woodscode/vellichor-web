"""Minimal password gate with a signed session cookie."""
import hashlib
import hmac
import os
import secrets

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

COOKIE = "vellichor_session"
MAX_AGE = 60 * 60 * 24 * 30  # 30 days

PASSWORD = os.environ.get("VELLICHOR_PASSWORD", "")
_secret = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
_signer = URLSafeTimedSerializer(_secret, salt="vellichor-auth")

# Auth is disabled entirely if no password is set.
ENABLED = bool(PASSWORD)


def check_password(candidate: str) -> bool:
    if not ENABLED:
        return True
    return hmac.compare_digest(
        hashlib.sha256(candidate.encode()).digest(),
        hashlib.sha256(PASSWORD.encode()).digest(),
    )


def make_token() -> str:
    return _signer.dumps({"ok": True})


def valid_token(token: str) -> bool:
    if not token:
        return False
    try:
        _signer.loads(token, max_age=MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def is_authed(request) -> bool:
    if not ENABLED:
        return True
    return valid_token(request.cookies.get(COOKIE, ""))
