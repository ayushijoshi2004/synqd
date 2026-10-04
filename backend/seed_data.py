"""Load local demo fixtures once when composing the API's repository."""

import json
from pathlib import Path

from meeting_model import Meeting, validate_meeting


def load_seed_meetings() -> list[Meeting]:
    path = Path(__file__).parent / "fixtures" / "meetings.json"
    return [validate_meeting(meeting) for meeting in json.loads(path.read_text(encoding="utf-8"))]
