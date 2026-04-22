from __future__ import annotations

import json
import base64
import hashlib
import hmac
import os
import sqlite3
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "marker_board.sqlite3"
TOKEN_TTL_SECONDS = 60 * 60 * 24


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def get_session_secret() -> str:
    return os.environ.get("SESSION_SECRET") or os.environ.get("BOARD_PASSWORD", "")


def create_session_token() -> str:
    secret = get_session_secret()
    if not secret:
        raise RuntimeError("SESSION_SECRET or BOARD_PASSWORD is required")

    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    encoded_payload = b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded_payload}.{b64url_encode(signature)}"


def verify_session_token(token: str) -> bool:
    secret = get_session_secret()
    if not secret or "." not in token:
        return False

    encoded_payload, encoded_signature = token.split(".", 1)
    expected_signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()

    try:
        provided_signature = b64url_decode(encoded_signature)
        payload = json.loads(b64url_decode(encoded_payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return False

    if not hmac.compare_digest(provided_signature, expected_signature):
        return False

    return int(payload.get("exp", 0)) >= int(time.time())


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def load_state() -> dict | None:
    with sqlite3.connect(DB_PATH) as connection:
        row = connection.execute(
            "SELECT payload, updated_at FROM app_state WHERE id = 1"
        ).fetchone()

    if not row:
        return None

    payload, updated_at = row
    data = json.loads(payload)
    data["_meta"] = {"updatedAt": updated_at}
    return data


def save_state(payload: dict) -> dict:
    serialized = json.dumps(payload, ensure_ascii=False)
    updated_at = utc_now_iso()

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO app_state (id, payload, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (serialized, updated_at),
        )
        connection.commit()

    return {"ok": True, "updatedAt": updated_at}


class MarkerBoardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)

        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return None

        return payload if isinstance(payload, dict) else None

    def _require_auth(self) -> bool:
        auth_header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        token = auth_header[len(prefix):].strip() if auth_header.startswith(prefix) else ""

        if verify_session_token(token):
            return True

        self._send_json(
            {"ok": False, "message": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
        return False

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            if not self._require_auth():
                return
            state = load_state()
            self._send_json({"ok": True, "state": state})
            return

        if parsed.path == "/":
            self.path = "/access_gate.html"

        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/auth":
            self._send_json(
                {"ok": False, "message": "Not found"},
                status=HTTPStatus.NOT_FOUND,
            )
            return

        configured_password = os.environ.get("BOARD_PASSWORD")
        if not configured_password:
            self._send_json(
                {"ok": False, "message": "BOARD_PASSWORD is not configured"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        payload = self._read_json()
        if payload is None:
            self._send_json(
                {"ok": False, "message": "Invalid JSON"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        if not hmac.compare_digest(str(payload.get("password", "")), configured_password):
            self._send_json(
                {"ok": False, "message": "비밀번호가 올바르지 않습니다."},
                status=HTTPStatus.UNAUTHORIZED,
            )
            return

        self._send_json({"ok": True, "token": create_session_token()})

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/state":
            self._send_json(
                {"ok": False, "message": "Not found"},
                status=HTTPStatus.NOT_FOUND,
            )
            return

        if not self._require_auth():
            return

        payload = self._read_json()
        if payload is None:
            self._send_json(
                {"ok": False, "message": "Invalid JSON"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        result = save_state(payload)
        self._send_json(result)


def run() -> None:
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), MarkerBoardHandler)
    print(f"Serving marker board on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
