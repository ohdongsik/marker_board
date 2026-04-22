from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from http import HTTPStatus


TOKEN_TTL_SECONDS = 60 * 60 * 24
STATE_ID = os.environ.get("SUPABASE_STATE_ID", "default")


def json_response(handler, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}

    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def get_session_secret() -> str:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise RuntimeError("SESSION_SECRET is not configured")
    return secret


def create_session_token() -> str:
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
        "scope": "marker-board",
    }
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        get_session_secret().encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64url_encode(signature)}"


def verify_session_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False

    encoded_payload, encoded_signature = token.split(".", 1)
    expected_signature = hmac.new(
        get_session_secret().encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    try:
        received_signature = _b64url_decode(encoded_signature)
        if not hmac.compare_digest(expected_signature, received_signature):
            return False

        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
        return payload.get("scope") == "marker-board" and int(payload.get("exp", 0)) > int(time.time())
    except (ValueError, json.JSONDecodeError):
        return False


def get_bearer_token(handler) -> str | None:
    authorization = handler.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ").strip()


def require_auth(handler) -> bool:
    try:
        is_valid = verify_session_token(get_bearer_token(handler))
    except RuntimeError as error:
        json_response(handler, {"ok": False, "message": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
        return False

    if not is_valid:
        json_response(handler, {"ok": False, "message": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
        return False

    return True


def get_supabase_config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    return url, key


def supabase_request(method: str, path: str, payload: dict | None = None) -> dict | list:
    url, key = get_supabase_config()
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{url}{path}",
        data=body,
        method=method,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8")
        raise RuntimeError(f"Supabase request failed: {error.code} {detail}") from error
