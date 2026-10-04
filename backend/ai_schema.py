"""Provider output contract. Evidence/participant references are not DB fields."""


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def array(items):
    return {"type": "array", "items": items}


TEXT = {"type": "string"}
PERSON_ID = {"type": ["string", "null"]}
EVIDENCE = array(obj({"entryIndex": {"type": "integer", "minimum": 0}, "quote": TEXT}))
INTELLIGENCE_SCHEMA = obj({
    "summary": obj({"beforeHighlight": TEXT, "highlight": TEXT, "afterHighlight": TEXT, "points": array(TEXT)}),
    "decisions": array(obj({"text": TEXT, "participantId": PERSON_ID, "note": TEXT, "evidence": EVIDENCE})),
    "actionItems": array(obj({
        "text": TEXT, "assigneeId": PERSON_ID, "due": TEXT,
        "status": {"type": "string", "enum": ["todo"]}, "evidence": EVIDENCE,
    })),
    "unresolvedItems": array(obj({"text": TEXT, "evidence": EVIDENCE})),
    "followUps": array(obj({
        "title": TEXT, "date": TEXT, "startTime": TEXT, "endTime": TEXT,
        "participantIds": array(TEXT), "agenda": TEXT,
        "status": {"type": "string", "enum": ["suggested"]}, "evidence": EVIDENCE,
    })),
    "agendaEntries": array(obj({
        "agendaIndex": {"type": "integer", "minimum": 0}, "title": TEXT,
        "completed": {"type": "boolean"}, "evidence": EVIDENCE,
    })),
})
