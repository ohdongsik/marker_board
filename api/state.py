from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler

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
            payload = supabase_request(
                "POST",
                "/rest/v1/rpc/get_marker_board_state",
                {
                    "workspace_id_input": STATE_ID,
                },
            )
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
                "/rest/v1/rpc/save_marker_board_state",
                {
                    "workspace_id_input": STATE_ID,
                    "state_input": payload,
                },
            )
            json_response(self, {"ok": True})
        except Exception as error:  # noqa: BLE001
            json_response(
                self,
                {"ok": False, "message": str(error)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
