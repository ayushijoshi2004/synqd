"""JSON validation matching frontend/src/types/meeting.ts.

Dates and times are local calendar values, as in the frontend. This model has
no participant-count limit; the eight-person policy belongs to the demo UI.
"""

from copy import deepcopy
from datetime import date
import re
from typing import Any

from meeting_errors import MeetingError

Meeting = dict[str, Any]
STATUSES = frozenset({"scheduled", "in_progress", "ended", "cancelled"})
AI_STATUSES = frozenset({"unprocessed", "processing", "processed", "failed"})
TASK_STATUSES = frozenset({"todo", "in_progress", "done"})
FOLLOW_UP_STATUSES = frozenset({"suggested", "approved", "dismissed"})
REQUIRED_POST_FIELDS = frozenset({"title", "date", "startTime", "endTime", "participants"})
CORE_FIELDS = frozenset({
    "id", "title", "date", "startTime", "endTime", "project", "team",
    "participants", "agenda", "status", "aiStatus", "preview",
})
MEETING_INPUT_FIELDS = CORE_FIELDS - {"id", "status", "aiStatus", "preview"}
DETAIL_FIELDS = frozenset({
    "agendaEntries", "summary", "transcript", "decisions", "actionItems",
    "projectOverview", "assistant", "followUps", "unresolvedItems", "googleCalendar", "googleMeetUrl", "transcription",
})
MEETING_FIELDS = CORE_FIELDS | DETAIL_FIELDS
PATCH_FIELDS = MEETING_FIELDS - {"id", "googleCalendar", "transcription"}


def _object(value, path, required, optional=()):
    if not isinstance(value, dict):
        raise MeetingError(f"{path} must be a JSON object.")
    missing = set(required) - value.keys()
    if missing:
        raise MeetingError(f"{path} is missing: {', '.join(sorted(missing))}.")
    unknown = value.keys() - (set(required) | set(optional))
    if unknown:
        raise MeetingError(f"{path} contains unsupported fields: {', '.join(sorted(unknown))}.")
    return value


def _text(value, path, *, nonempty=False):
    if not isinstance(value, str) or (nonempty and not value.strip()):
        requirement = "a non-empty string" if nonempty else "a string"
        raise MeetingError(f"{path} must be {requirement}.")


def _array(value, path):
    if not isinstance(value, list):
        raise MeetingError(f"{path} must be an array.")
    return value


def _strings(value, path):
    for index, item in enumerate(_array(value, path)):
        _text(item, f"{path}[{index}]")


def _enum(value, path, allowed):
    if not isinstance(value, str) or value not in allowed:
        raise MeetingError(f"{path} must be one of: {', '.join(sorted(allowed))}.")


def _participant(value, path):
    _object(value, path, {"id", "name", "color"}, {"email"})
    if "email" in value:
        if not isinstance(value["email"], str) or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value["email"]):
            raise MeetingError(f"{path}.email must be a valid email address.")
    for field in ("id", "name", "color"):
        _text(value[field], f"{path}.{field}", nonempty=True)


def _detail(meeting):
    if "googleMeetUrl" in meeting:
        url = meeting["googleMeetUrl"]
        if not isinstance(url, str) or (url and not re.fullmatch(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}/?(?:\?[^\s#]*)?", url)):
            raise MeetingError("googleMeetUrl must be a valid HTTPS Google Meet link or an empty string.")
    if "transcription" in meeting:
        state = meeting["transcription"]
        if not isinstance(state, dict) or not isinstance(state.get("id"), str):
            raise MeetingError("Invalid transcription session.")
        _enum(state.get("status"), "transcription.status", {"starting", "transcribing", "stopping", "completed", "error"})

    if "googleCalendar" in meeting:
        calendar = _object(meeting["googleCalendar"], "googleCalendar", {"status"},
                           {"accountId", "timeZone", "eventId", "eventUrl", "error"})
        _enum(calendar["status"], "googleCalendar.status", {"not_connected", "pending", "failed", "created"})
        for field in calendar.keys() - {"status"}:
            _text(calendar[field], f"googleCalendar.{field}", nonempty=True)
        if calendar["status"] == "created" and not all(calendar.get(key) for key in ("eventId", "eventUrl")):
            raise MeetingError("Created Calendar events must contain Google-returned metadata.")

    for name in ("agendaEntries", "transcript", "decisions", "actionItems"):
        if name not in meeting:
            continue
        seen_ids = set()
        for index, item in enumerate(_array(meeting[name], name)):
            path = f"{name}[{index}]"
            if name == "agendaEntries":
                _object(item, path, {"title", "timestamp", "completed"})
                _text(item["title"], f"{path}.title", nonempty=True)
                _text(item["timestamp"], f"{path}.timestamp")
                if type(item["completed"]) is not bool:
                    raise MeetingError(f"{path}.completed must be a boolean.")
            elif name == "transcript":
                _object(item, path, {"timestamp", "speaker", "text"})
                _text(item["timestamp"], f"{path}.timestamp")
                _text(item["text"], f"{path}.text")
                _participant(item["speaker"], f"{path}.speaker")
            elif name == "decisions":
                _object(item, path, {"id", "text", "participant", "timestamp", "note"})
                for field in ("id", "text", "timestamp", "note"):
                    _text(item[field], f"{path}.{field}", nonempty=field == "id")
                if item["participant"] is not None:
                    _participant(item["participant"], f"{path}.participant")
            else:
                _object(item, path, {"id", "text", "assignee", "due", "status"}, {"jiraIssueKey", "jiraIssueUrl"})
                for field in ("id", "text", "due", "jiraIssueKey", "jiraIssueUrl"):
                    if field in item:
                        _text(item[field], f"{path}.{field}", nonempty=field == "id")
                if item["assignee"] is not None:
                    _participant(item["assignee"], f"{path}.assignee")
                _enum(item["status"], f"{path}.status", TASK_STATUSES)
            if name in ("decisions", "actionItems"):
                if item["id"] in seen_ids:
                    raise MeetingError(f"{name} must have unique ids.")
                seen_ids.add(item["id"])

    if "summary" in meeting:
        summary = _object(meeting["summary"], "summary", {"beforeHighlight", "highlight", "afterHighlight", "points"})
        for field in ("beforeHighlight", "highlight", "afterHighlight"):
            _text(summary[field], f"summary.{field}")
        _strings(summary["points"], "summary.points")

    if "projectOverview" in meeting:
        text_fields = {"name", "description", "previousLaunchDate", "launchDate"}
        list_fields = {"resources", "relatedResources"}
        count_fields = {"additionalResourceCount", "previousMeetingCount"}
        project = _object(meeting["projectOverview"], "projectOverview", text_fields | list_fields | count_fields, {"jiraProjectUrl"})
        for field in text_fields | {"jiraProjectUrl"}:
            if field in project:
                _text(project[field], f"projectOverview.{field}")
        for field in list_fields:
            _strings(project[field], f"projectOverview.{field}")
        for field in count_fields:
            if type(project[field]) is not int or project[field] < 0:
                raise MeetingError(f"projectOverview.{field} must be a non-negative integer.")

    if "assistant" in meeting:
        assistant = _object(meeting["assistant"], "assistant", {"scopeLabel", "suggestions"})
        _text(assistant["scopeLabel"], "assistant.scopeLabel")
        _strings(assistant["suggestions"], "assistant.suggestions")

    if "unresolvedItems" in meeting:
        _strings(meeting["unresolvedItems"], "unresolvedItems")

    if "followUps" in meeting:
        seen_ids = set()
        for index, follow_up in enumerate(_array(meeting["followUps"], "followUps")):
            path = f"followUps[{index}]"
            _object(follow_up, path, MEETING_INPUT_FIELDS | {"id", "status", "sourceMeetingId"}, {"scheduledMeetingId"})
            _enum(follow_up["status"], f"{path}.status", FOLLOW_UP_STATUSES)
            if follow_up["sourceMeetingId"] != meeting["id"]:
                raise MeetingError(f"{path}.sourceMeetingId must match the source meeting id.")
            # Reuse the core meeting validation without recursively adding details.
            fields = validate_meeting({
                **{field: follow_up[field] for field in MEETING_INPUT_FIELDS | {"id"}},
                "status": "scheduled", "aiStatus": "unprocessed", "preview": "",
            }, allow_unscheduled=follow_up["status"] != "approved")
            for field in MEETING_INPUT_FIELDS:
                follow_up[field] = fields[field]
            if follow_up["id"] in seen_ids:
                raise MeetingError("followUps must have unique ids within the source meeting.")
            seen_ids.add(follow_up["id"])
            if follow_up["status"] == "approved":
                _text(follow_up.get("scheduledMeetingId"), f"{path}.scheduledMeetingId", nonempty=True)
            elif "scheduledMeetingId" in follow_up:
                raise MeetingError(f"{path}.scheduledMeetingId is only valid for an approved follow-up.")


def validate_meeting(value: Any, *, allow_unscheduled: bool = False) -> Meeting:
    """Validate a complete record and return an isolated, normalized copy."""
    _object(value, "meeting", CORE_FIELDS, DETAIL_FIELDS)
    result = deepcopy(value)
    for field in CORE_FIELDS - {"participants"}:
        _text(result[field], field, nonempty=field in {"id", "title"})
    if not re.fullmatch(r"[A-Za-z0-9_-]+", result["id"]):
        raise MeetingError("id may contain only letters, numbers, underscores, and hyphens.")
    for field in ("title", "project", "team", "agenda"):
        result[field] = result[field].strip()
    if result["date"] or not allow_unscheduled:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", result["date"]):
            raise MeetingError("date must be a valid YYYY-MM-DD date.")
        try:
            date.fromisoformat(result["date"])
        except ValueError as exc:
            raise MeetingError("date must be a valid YYYY-MM-DD date.") from exc
    for field in ("startTime", "endTime"):
        if allow_unscheduled and not result[field]:
            continue
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", result[field]):
            raise MeetingError(f"{field} must be a valid HH:mm time.")
    if result["endTime"] and result["startTime"] and result["endTime"] <= result["startTime"]:
        raise MeetingError("endTime must be after startTime on the same date.")
    _enum(result["status"], "status", STATUSES)
    _enum(result["aiStatus"], "aiStatus", AI_STATUSES)
    people = _array(result["participants"], "participants")
    if not people and not allow_unscheduled:
        raise MeetingError("participants must contain at least one participant.")
    ids, names = set(), set()
    for index, person in enumerate(people):
        _participant(person, f"participants[{index}]")
        person["name"] = person["name"].strip()
        if person["id"] in ids or person["name"].casefold() in names:
            raise MeetingError("participants must have unique ids and names.")
        ids.add(person["id"])
        names.add(person["name"].casefold())
    _detail(result)
    return result


def validate_post_fields(value: Any) -> None:
    _object(value, "meeting", REQUIRED_POST_FIELDS, (MEETING_FIELDS - REQUIRED_POST_FIELDS) - {"googleCalendar", "transcription"})


def validate_patch_fields(value: Any) -> None:
    _object(value, "patch", (), PATCH_FIELDS)
    if not value:
        raise MeetingError("Supply at least one field to update.")


def validate_follow_up_edits(value: Any) -> None:
    _object(value, "follow-up edits", (), MEETING_INPUT_FIELDS)
