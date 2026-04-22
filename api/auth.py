from __future__ import annotations

import hmac
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler

from api._shared import create_session_token, json_response, read_json_body


class handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        try:
            board_password = os.environ.get("BOARD_PASSWORD")
            if not board_password:
                json_response(
                    self,
                    {"ok": False, "message": "BOARD_PASSWORD is not configured"},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            payload = read_json_body(self)
            password = str(payload.get("password", ""))
            if not hmac.compare_digest(password, board_password):
                json_response(
                    self,
                    {"ok": False, "message": "Invalid password"},
                    HTTPStatus.UNAUTHORIZED,
                )
                return

            token = create_session_token()
            json_response(self, {"ok": True, "token": token})
        except Exception as error:  # noqa: BLE001
            json_response(
                self,
                {"ok": False, "message": str(error)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_GET(self):  # noqa: N802
        json_response(
            self,
            {"ok": False, "message": "Method not allowed"},
            HTTPStatus.METHOD_NOT_ALLOWED,
        )
