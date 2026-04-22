from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote

from api._shared import (
    STATE_ID,
    json_response,
    read_json_body,
    require_auth,
    supabase_request,
)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if not require_auth(self):
            return

        try:
            rows = supabase_request(
                "GET",
                f"/rest/v1/marker_board_states?id=eq.{quote(STATE_ID)}&select=payload",
            )
            payload = rows[0]["payload"] if rows else None
            json_response(self, {"ok": True, "state": payload})
        except Exception as error:  # noqa: BLE001
            json_response(
                self,
                {"ok": False, "message": str(error)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_PUT(self):  # noqa: N802
        if not require_auth(self):
            return

        try:
            payload = read_json_body(self)
            if not isinstance(payload, dict):
                json_response(
                    self,
                    {"ok": False, "message": "Payload must be an object"},
                    HTTPStatus.BAD_REQUEST,
                )
                return

            supabase_request(
                "POST",
                "/rest/v1/marker_board_states",
                {
                    "id": STATE_ID,
                    "payload": payload,
                },
            )
            json_response(self, {"ok": True})
        except Exception as error:  # noqa: BLE001
            json_response(
                self,
                {"ok": False, "message": str(error)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
