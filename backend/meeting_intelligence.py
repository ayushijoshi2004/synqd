"""Validate provider data, ground references, normalize to existing Synq types."""

from copy import deepcopy
from datetime import date, timedelta
import re
from uuid import NAMESPACE_URL, uuid5

from ai_schema import INTELLIGENCE_SCHEMA
from meeting_model import validate_meeting


class InvalidIntelligence(ValueError):
    pass


def validate_shape(value, schema, path="result"):
    """Validate the small JSON Schema subset used by our provider contract."""
    kind = schema["type"]
    if isinstance(kind, list):
        if value is None and "null" in kind:
            return
        kind = next(item for item in kind if item != "null")
    expected = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int}[kind]
    if type(value) is not expected:
        raise InvalidIntelligence(f"{path} has an invalid type.")
    if "enum" in schema and value not in schema["enum"]:
        raise InvalidIntelligence(f"{path} has an invalid value.")
    if kind == "object":
        if set(value) != set(schema["properties"]):
            raise InvalidIntelligence(f"{path} has missing or unsupported fields.")
        for key, field in schema["properties"].items():
            validate_shape(value[key], field, f"{path}.{key}")
    elif kind == "array":
        for item in value:
            validate_shape(item, schema["items"], path)
    elif kind == "integer" and value < schema.get("minimum", value):
        raise InvalidIntelligence(f"{path} is out of range.")


def processing_context(meeting):
    return deepcopy({
        key: meeting.get(key, [] if key in ("transcript", "agendaEntries", "participants") else "")
        for key in ("id", "title", "date", "project", "team", "participants", "transcript", "agendaEntries")
    })


def _identity(text):
    return " ".join(text.casefold().split())


def _id(meeting_id, kind, text):
    return str(uuid5(NAMESPACE_URL, f"synq:{meeting_id}:{kind}:{_identity(text)}"))


def _grounded_date(value, quote, reference):
    """Conservative date grounding. Ambiguous/unrecognized timing must stay blank."""
    proposed, baseline = date.fromisoformat(value), date.fromisoformat(reference)
    if re.search(rf"\b{re.escape(value)}\b", quote):
        return True
    day = rf"{proposed.day}(?:st|nd|rd|th)?"
    month = rf"(?:{proposed.strftime('%B')}|{proposed.strftime('%b')})\.?"
    calendar_date = rf"(?:{month}\s+{day}|{day}\s+{month}|{proposed.month}/{proposed.day})"
    # A named date without a year means the next occurrence, not any arbitrary year.
    match = re.search(rf"\b{calendar_date}(?!\d)(?:,?\s+(\d{{4}}))?", quote, re.I)
    if match:
        if match.group(1):
            return proposed.year == int(match.group(1))
        return 0 <= (proposed - baseline).days <= 366
    relative = (("day after tomorrow", 2), ("tomorrow", 1), ("today", 0))
    for phrase, offset in relative:
        if re.search(rf"\b{phrase}\b", quote, re.I):
            return proposed == baseline + timedelta(days=offset)
    weekday = proposed.strftime("%A")
    match = re.search(rf"\b(?:(next)\s+)?{weekday}\b", quote, re.I)
    return bool(match and 0 <= (proposed - baseline).days <= (14 if match.group(1) else 7))


def normalize_intelligence(raw, meeting):
    validate_shape(raw, INTELLIGENCE_SCHEMA)
    transcript = meeting["transcript"]
    people = {person["id"]: person for person in meeting["participants"]}
    people.update({line["speaker"]["id"]: line["speaker"] for line in transcript})

    def person(person_id):
        if person_id is None:
            return None
        if person_id not in people:
            raise InvalidIntelligence("Unknown participant reference.")
        return deepcopy(people[person_id])

    def evidence(items, *, required=True, substantive=False):
        if required and not items:
            raise InvalidIntelligence("Evidence is required.")
        for item in items:
            index, quote = item["entryIndex"], item["quote"].strip()
            if index >= len(transcript) or not quote or quote not in transcript[index]["text"]:
                raise InvalidIntelligence("Evidence must quote an existing transcript entry.")
            if substantive and len(quote.split()) < 4:
                raise InvalidIntelligence("Agenda completion needs substantive evidence.")
        return " ".join(item["quote"] for item in items)

    def timestamp(items, previous=""):
        for item in items:
            value = transcript[item["entryIndex"]]["timestamp"]
            if re.fullmatch(r"(?:\d{1,3}:[0-5]\d:[0-5]\d|\d{1,3}:[0-5]\d)", value):
                return value
        return previous

    def text(value):
        if not value.strip():
            raise InvalidIntelligence("Extracted items must have non-empty text.")
        return value.strip()

    summary = deepcopy(raw["summary"])
    if not "".join(summary[key] for key in ("beforeHighlight", "highlight", "afterHighlight")).strip():
        raise InvalidIntelligence("Summary must not be empty.")
    decisions = []
    for item in raw["decisions"]:
        evidence(item["evidence"])
        decisions.append({
            "id": _id(meeting["id"], "decision", item["text"]), "text": text(item["text"]),
            "participant": person(item["participantId"]), "note": item["note"].strip(),
            "timestamp": timestamp(item["evidence"]),
        })
    actions = []
    for item in raw["actionItems"]:
        quote = evidence(item["evidence"])
        due = item["due"].strip()

        # Keep the action item, but remove a due date that isn't
        # supported by the cited transcript evidence.
        if due and due.casefold() not in quote.casefold():
            due = ""

        actions.append({
            "id": _id(meeting["id"], "action", item["text"]),
            "text": text(item["text"]),
            "assignee": person(item["assigneeId"]),
            "due": due,
            "status": "todo",
        })
    unresolved = []
    for item in raw["unresolvedItems"]:
        evidence(item["evidence"])
        unresolved.append(text(item["text"]))
    follow_ups = []
    for item in raw["followUps"]:
        quote = evidence(item["evidence"])
        # Unknown scheduling values stay empty; never supply a demo default.
        if item["date"] and not _grounded_date(item["date"], quote, meeting["date"]):
            raise InvalidIntelligence("Follow-up date has no timing evidence.")
        for field in ("startTime",):
            if not item[field]:
                continue
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item[field]):
                raise InvalidIntelligence("Invalid follow-up time.")
            hour, minute = map(int, item[field].split(":"))
            suffix = r"a\.?m\.?" if hour < 12 else r"p\.?m\.?"
            clock = rf"{hour % 12 or 12}(?::{minute:02d})?\s*{suffix}" if minute == 0 else rf"{hour % 12 or 12}:{minute:02d}\s*{suffix}"
            if not re.search(rf"\b(?:{hour:02d}:{minute:02d}|{hour}:{minute:02d}|{clock})\b", quote, re.I):
                raise InvalidIntelligence("Follow-up time must appear in its evidence.")
        follow_ups.append({
            "id": _id(meeting["id"], "follow-up", item["title"]), "title": text(item["title"]),
            **{field: item[field] for field in ("date", "startTime", "endTime", "agenda")},
            "participants": [person(person_id) for person_id in item["participantIds"]],
            "project": meeting["project"], "team": meeting["team"],
            "status": "suggested", "sourceMeetingId": meeting["id"],
        })
    agenda = deepcopy(meeting.get("agendaEntries", []))
    if len(raw["agendaEntries"]) != len(agenda):
        raise InvalidIntelligence("Agenda results must match every existing entry.")
    seen = set()
    for item in raw["agendaEntries"]:
        index = item["agendaIndex"]
        if index >= len(agenda) or index in seen or item["title"] != agenda[index]["title"]:
            raise InvalidIntelligence("AI cannot replace or invent agenda entries.")
        seen.add(index)
        evidence(item["evidence"], required=item["completed"], substantive=item["completed"])
        agenda[index]["completed"] = item["completed"]
        if item["completed"]:
            agenda[index]["timestamp"] = timestamp(item["evidence"], agenda[index]["timestamp"])
    result = {
        "summary": summary, "decisions": decisions, "actionItems": actions,
        "unresolvedItems": list(dict.fromkeys(unresolved)), "followUps": follow_ups, "agendaEntries": agenda,
    }
    validate_meeting({**meeting, **result})
    return result


def merge_intelligence(current, result):
    """Refresh analysis while preserving task IDs/statuses, Jira and resolutions."""
    merged = deepcopy(current)
    for field in ("summary", "decisions", "agendaEntries", "unresolvedItems"):
        merged[field] = deepcopy(result[field])
    for field, key in (("actionItems", "text"), ("followUps", "title")):
        existing = merged.setdefault(field, [])
        ids = {item["id"] for item in existing}
        texts = {_identity(item[key]) for item in existing}
        for item in result[field]:
            if item["id"] not in ids and _identity(item[key]) not in texts:
                existing.append(deepcopy(item))
                ids.add(item["id"])
                texts.add(_identity(item[key]))
    merged["aiStatus"] = "processed"
    return validate_meeting(merged)