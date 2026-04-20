from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "marker_board.sqlite3"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            state = load_state()
            self._send_json({"ok": True, "state": state})
            return

        if parsed.path == "/":
            self.path = "/access_gate.html"

        super().do_GET()

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/state":
            self._send_json(
                {"ok": False, "message": "Not found"},
                status=HTTPStatus.NOT_FOUND,
            )
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)

        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(
                {"ok": False, "message": "Invalid JSON"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        if not isinstance(payload, dict):
            self._send_json(
                {"ok": False, "message": "Payload must be an object"},
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
