import base64
import hashlib
import hmac
import json
import time

from app.config import get_settings


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def create_access_token(email: str) -> str:
    settings = get_settings()
    payload = _encode(json.dumps({"sub": email, "exp": int(time.time()) + 8 * 3600}).encode())
    signature = _encode(hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def valid_access_token(token: str) -> bool:
    settings = get_settings()
    if len(token) > 2048:
        return False
    try:
        payload, signature = token.split(".", 1)
        expected = _encode(hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return False
        decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return decoded.get("sub") == settings.admin_email and decoded.get("exp", 0) > time.time()
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
