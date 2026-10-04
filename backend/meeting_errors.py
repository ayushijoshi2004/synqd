"""Errors shared by the domain, storage adapter, and HTTP boundary."""


class MeetingError(Exception):
    status_code = 400
    code = "invalid_meeting"


class MeetingNotFound(MeetingError):
    status_code = 404
    code = "meeting_not_found"

    def __init__(self):
        super().__init__("Meeting not found.")


class MeetingAlreadyExists(MeetingError):
    status_code = 409
    code = "meeting_already_exists"

    def __init__(self):
        super().__init__("A meeting with that id already exists.")


class FollowUpNotFound(MeetingError):
    status_code = 404
    code = "follow_up_not_found"

    def __init__(self):
        super().__init__("Follow-up not found.")


class FollowUpConflict(MeetingError):
    status_code = 409
    code = "follow_up_conflict"


class ActionItemNotFound(MeetingError):
    status_code = 404
    code = "action_item_not_found"

    def __init__(self):
        super().__init__("Action item not found.")


class JiraCreateFailed(MeetingError):
    status_code = 502
    code = "jira_error"

    def __init__(self):
        super().__init__("Unable to create the Jira issue.")


class MeetingWriteConflict(MeetingError):
    status_code = 409
    code = "meeting_changed"

    def __init__(self):
        super().__init__("The meeting changed during this request. Please retry.")


class AIProcessingConflict(MeetingError):
    status_code = 409
    code = "ai_processing_conflict"


class AIProcessingFailed(MeetingError):
    status_code = 503
    code = "ai_processing_failed"

    def __init__(self):
        super().__init__("AI processing unavailable. Your meeting and transcript are still saved.")
