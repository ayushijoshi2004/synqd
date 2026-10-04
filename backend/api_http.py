"""Small JSON boundary helpers for Azure Functions HTTP handlers."""

from collections.abc import Callable
import json
import logging
from typing import Any

import azure.functions as func

from meeting_errors import MeetingError


def read_body(req: func.HttpRequest) -> Any:
    try:
        return req.get_json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise MeetingError("Request body must contain valid JSON.") from exc


def json_response(body: Any, status_code: int = 200, headers=None) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, ensure_ascii=False, allow_nan=False),
        mimetype="application/json",
        status_code=status_code,
        headers=headers,
    )


def respond(operation: Callable[[], Any], *, created: bool = False) -> func.HttpResponse:
    try:
        result = operation()
        headers = {"Location": f"/api/meetings/{result['id']}"} if created else None
        return json_response(result, 201 if created else 200, headers)
    except MeetingError as exc:
        return json_response({"error": {"code": exc.code, "message": str(exc)}}, exc.status_code)
    except Exception:
        logging.exception("Unexpected meeting API failure")
        return json_response({"error": {"code": "internal_error", "message": "Unable to complete the request."}}, 500)
