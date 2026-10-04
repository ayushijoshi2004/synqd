"""Vexa boundary. Credentials and upstream payloads stay on the backend."""

import os
import re
from urllib.parse import urlsplit

import requests

from meeting_errors import MeetingError


class VexaError(MeetingError):
    def __init__(self, message, code="vexa_error", status_code=502, *, safe_to_retry=False):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.safe_to_retry = safe_to_retry


def parse_meeting_id(value):
    if isinstance(value, str):
        value = value.strip()
        if re.fullmatch(r"[a-z]{3}-[a-z]{4}-[a-z]{3}", value):
            return value
        try:
            url = urlsplit(value)
            if (url.scheme == "https" and url.netloc == "meet.google.com"
                    and re.fullmatch(r"/[a-z]{3}-[a-z]{4}-[a-z]{3}/?", url.path)):
                return url.path.strip("/")
        except ValueError:
            pass
    raise VexaError("Enter a valid Google Meet URL or meeting ID.", "invalid_meeting_url", 400)


def _request(method, path, key_name, **kwargs):
    key = os.environ.get(key_name, "").strip()
    if not key:
        raise VexaError(f"{key_name} is not configured.", "vexa_not_configured", 503, safe_to_retry=True)
    base = os.environ.get("VEXA_API_BASE", "https://api.cloud.vexa.ai").strip().rstrip("/")
    try:
        url = urlsplit(base)
        valid = url.scheme == "https" and bool(url.hostname) and not (url.username or url.password or url.query or url.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise VexaError("Vexa API base configuration is invalid.", "vexa_not_configured", 503, safe_to_retry=True)
    try:
        response = requests.request(
            method, base + path,
            headers={"X-API-Key": key, "Content-Type": "application/json", "Accept": "application/json"},
            timeout=20, allow_redirects=False, **kwargs,
        )
    except requests.Timeout:
        raise VexaError("Vexa request timed out.", "vexa_timeout", 504) from None
    except requests.RequestException:
        raise VexaError("Unable to reach Vexa.", "vexa_unavailable", 502) from None
    status = response.status_code
    if status == 401:
        raise VexaError("Vexa rejected the configured API key.", "vexa_authentication_error", safe_to_retry=True)
    if status == 403:
        raise VexaError("The Vexa key lacks permission or scope for this operation.", "vexa_permission_error", safe_to_retry=True)
    if status == 404 and method == "GET":
        raise VexaError("Transcript not found yet. The bot may still be joining.", "transcript_not_found", 404)
    if not 200 <= status < 300:
        raise VexaError(
        f"Vexa could not complete the request. Status: {status}. Response: {response.text}",
        "vexa_upstream_error"
    )
    try:
        data = response.json()
    except ValueError:
        raise VexaError("Vexa returned an invalid response.", "vexa_invalid_response") from None
    if not isinstance(data, dict):
        raise VexaError("Vexa returned an invalid response.", "vexa_invalid_response")
    return data


def join_meeting(body):
    meeting_id = parse_meeting_id(body.get("meetingUrl") if isinstance(body, dict) else None)

    data = _request("POST", "/bots", "VEXA_BOT_KEY", json={
        "platform": "google_meet",
        "native_meeting_id": meeting_id,
        "bot_name": "Synq AI",
        "recording_enabled": True,
        "transcribe_enabled": True,
        "transcription_tier": "realtime",
    })

    if type(data.get("id")) is not int or data["id"] <= 0:
        raise VexaError("Vexa returned an invalid bot response.", "vexa_invalid_response")

    return {
        "id": data["id"],
        "meetingId": meeting_id,
        "status": "requested"
    }


def get_transcript(meeting_id):
    meeting_id = parse_meeting_id(meeting_id)
    data = _request("GET", f"/transcripts/google_meet/{meeting_id}", "VEXA_TRANSCRIPT_KEY")
    segments = data.get("segments")
    if not isinstance(segments, list):
        raise VexaError("Vexa returned an invalid transcript.", "vexa_invalid_response")
    result = []
    fields = {"id": "segment_id", "speaker": "speaker", "text": "text",
              "startTime": "absolute_start_time", "endTime": "absolute_end_time"}
    for segment in segments:
        if not isinstance(segment, dict):
            raise VexaError("Vexa returned an invalid transcript segment.", "vexa_invalid_response")
        if segment.get("completed") is not True:
            continue
        if not all(isinstance(segment.get(source), str) for source in fields.values()):
            raise VexaError("Vexa returned an invalid completed segment.", "vexa_invalid_response")
        result.append({**{target: segment[source] for target, source in fields.items()}, "completed": True})
    return result


def check_configuration():
    # Check both scoped credentials before creating a bot we cannot transcribe.
    for name in ("VEXA_BOT_KEY", "VEXA_TRANSCRIPT_KEY"):
        if not os.environ.get(name, "").strip():
            raise VexaError(f"{name} is not configured.", "vexa_not_configured", 503, safe_to_retry=True)


def get_session(bot_id, native_id):
    """Never read a native-link transcript: it may now belong to another run."""
    import math
    data = _request("GET", f"/transcripts/by-id/{bot_id}", "VEXA_TRANSCRIPT_KEY")
    if (type(data.get("id")) is not int or data["id"] != bot_id
            or data.get("native_meeting_id") != native_id or data.get("platform") != "google_meet"
            or data.get("status") not in {"requested", "joining", "awaiting_admission", "needs_help", "active", "stopping", "completed", "failed"}
            or not isinstance(data.get("segments"), list)):
        raise VexaError("Vexa did not confirm the saved transcription session. No transcript was attached.", "vexa_session_mismatch")
    segments = []
    for segment in data["segments"]:
        if not isinstance(segment, dict):
            raise VexaError("Vexa returned an invalid transcript segment.", "vexa_invalid_response")
        if segment.get("completed") is not True:
            continue
        if (not isinstance(segment.get("segment_id"), str) or not segment["segment_id"]
                or not isinstance(segment.get("text"), str) or not isinstance(segment.get("speaker"), str)):
            raise VexaError("Vexa returned an invalid completed segment.", "vexa_invalid_response")
        start = segment.get("start")
        if type(start) in (int, float) and math.isfinite(start) and start >= 0:
            seconds = int(start)
            timestamp = f"{seconds // 60:02d}:{seconds % 60:02d}"
        elif isinstance(segment.get("absolute_start_time"), str):
            from datetime import datetime
            try:
                stamp = datetime.fromisoformat(segment["absolute_start_time"].replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    raise ValueError()
                timestamp = stamp.isoformat()
            except ValueError:
                raise VexaError("Vexa returned an invalid segment time.", "vexa_invalid_response") from None
        else:
            raise VexaError("Vexa returned an invalid segment time.", "vexa_invalid_response")
        segments.append({"id": segment["segment_id"], "speaker": segment["speaker"],
                         "text": segment["text"], "timestamp": timestamp})
    return {"status": data["status"], "segments": segments}


def stop_session(bot_id, native_id):
    # Vexa's stop endpoint is native-key-only. Verify that it still addresses our
    # exact record before sending DELETE. Synq also holds a durable link claim.
    latest = _request("GET", f"/transcripts/google_meet/{native_id}", "VEXA_TRANSCRIPT_KEY")
    if latest.get("id") != bot_id or latest.get("platform") != "google_meet" or latest.get("native_meeting_id") != native_id:
        raise VexaError("The Meet link now belongs to a different Vexa session. Synq did not stop that bot.", "vexa_session_mismatch")
    if latest.get("status") in {"completed", "failed"}:
        return
    data = _request("DELETE", f"/bots/google_meet/{native_id}", "VEXA_BOT_KEY")
    if data.get("meeting_id") != bot_id or data.get("status") != "stopping":
        raise VexaError("Vexa did not confirm the requested bot stop. Synq will check again.", "vexa_invalid_response")
