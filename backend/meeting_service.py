"""Meeting operations, independent of Azure Functions and storage technology."""

from copy import deepcopy
import logging
from typing import Any
from uuid import uuid4

from meeting_errors import (
    ActionItemNotFound, FollowUpConflict, FollowUpNotFound, JiraCreateFailed,
    AIProcessingConflict, AIProcessingFailed, MeetingError, MeetingWriteConflict,
)
from ai_provider import AIProvider, create_ai_provider
from meeting_intelligence import merge_intelligence, normalize_intelligence, processing_context
from meeting_model import (
    MEETING_INPUT_FIELDS, Meeting, validate_follow_up_edits, validate_meeting,
    validate_patch_fields, validate_post_fields,
)
from meeting_repository import MeetingRepository


class MeetingService:
    def __init__(self, repository: MeetingRepository, ai_provider: AIProvider | None = None, calendar_factory=None):
        self.repository = repository
        self.ai_provider = ai_provider
        self.calendar_factory = calendar_factory
        from transcription_service import TranscriptionService
        self.transcription = TranscriptionService(repository)

    def list(self) -> list[Meeting]:
        return self.repository.list()

    def get(self, meeting_id: str) -> Meeting:
        return self.repository.get(meeting_id)

    def ask(self, meeting_id: str, payload: Any) -> dict[str, str]:
        from meeting_assistant import answer_question, validate_question
        from meeting_errors import MeetingNotFound
        import re

        question, history = validate_question(payload)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", meeting_id) or meeting_id.startswith("__synq_"):
            raise MeetingNotFound()
        meeting = self.get(meeting_id)
        return answer_question(meeting, question, history)

    def create(self, payload: Any) -> Meeting:
        validate_post_fields(payload)
        meeting = {
            "id": str(uuid4()),
            "project": "",
            "team": "",
            "agenda": "",
            "status": "scheduled",
            "aiStatus": "unprocessed",
            "preview": "",
            **deepcopy(payload),
        }
        return self.repository.create(validate_meeting(meeting))

    def patch(self, meeting_id: str, payload: Any) -> Meeting:
        def change(current: Meeting) -> Meeting:
            validate_patch_fields(payload)
            state = current.get("transcription", {})
            if state.get("attempted") and not state.get("terminal") and {"googleMeetUrl", "transcript"} & payload.keys():
                raise MeetingError("End transcription before replacing its Meet link or transcript.")
            # Only supplied fields replace existing values. Lists and nested
            # objects are whole-field replacements, not recursive merge patches.
            updated = validate_meeting({**current, **deepcopy(payload)})
            if "followUps" in payload:
                # Appending a demo suggestion must not overwrite a concurrent
                # approval/dismissal or reset a resolved suggestion for approval.
                incoming = {item["id"]: item for item in updated["followUps"]}
                for previous in current.get("followUps", []):
                    next_item = incoming.get(previous["id"])
                    if next_item is None or any(
                        next_item.get(field) != previous.get(field)
                        for field in ("status", "scheduledMeetingId")
                    ):
                        raise FollowUpConflict("Follow-up state changed. Reload before updating suggestions.")
            return updated

        return self.repository.update(meeting_id, change)

    def delete(self, meeting_id: str) -> dict[str, Any]:
        current = self.repository.get(meeting_id)
        state = current.get("transcription", {})
        if state and not state.get("terminal") and (state.get("attempted") or state.get("status") in {"starting", "transcribing", "stopping"}):
            raise MeetingError("End transcription before deleting this meeting.")
        if state.get("terminal"):
            self.transcription.release(current)
        self.repository.delete(meeting_id)
        return {"id": meeting_id, "deleted": True}

    def dismiss_follow_up(self, meeting_id: str, follow_up_id: str) -> Meeting:
        def change(current: Meeting) -> Meeting:
            follow_up = self._suggested_follow_up(current, follow_up_id)
            follow_up["status"] = "dismissed"
            return validate_meeting(current)

        return self.repository.update(meeting_id, change)

    def approve_follow_up(self, meeting_id: str, follow_up_id: str, edits: Any) -> dict[str, Meeting]:
        result: dict[str, Meeting] = {}

        def change(current: Meeting) -> Meeting:
            follow_up = self._suggested_follow_up(current, follow_up_id)
            validate_follow_up_edits(edits)
            scheduled = validate_meeting({
                **{field: follow_up[field] for field in MEETING_INPUT_FIELDS},
                **deepcopy(edits),
                "id": str(uuid4()), "status": "scheduled",
                "aiStatus": "unprocessed", "preview": "",
            })
            follow_up.update({field: scheduled[field] for field in MEETING_INPUT_FIELDS})
            follow_up.update(status="approved", scheduledMeetingId=scheduled["id"])
            source = validate_meeting(current)
            # The local repository holds its reentrant lock throughout update(),
            # including create(). Validate both records before writing either;
            # a concurrent approve/dismiss cannot pass the suggested-state check.
            result["meeting"] = self.repository.create(scheduled)
            return source

        try:
            result["sourceMeeting"] = self.repository.update(meeting_id, change)
        except MeetingWriteConflict:
            # A concurrent AI/Jira edit won the source write. Do not leave the
            # meeting created by this unsuccessful approval as an orphan.
            if "meeting" in result:
                self.repository.delete(result["meeting"]["id"])
            raise
        if self.calendar_factory is not None:
            try:
                result["meeting"] = self.sync_follow_up_calendar(meeting_id, follow_up_id)
            except Exception:
                # Even a storage read failing after approval must not make the
                # successful Synq scheduling look like an unapproved suggestion.
                result["meeting"]["googleCalendar"] = {
                    "status": "failed",
                    "error": "Synq meeting saved. Google Calendar could not be checked. Reload and retry Calendar creation.",
                }
        return result

    def sync_follow_up_calendar(self, meeting_id: str, follow_up_id: str) -> Meeting:
        """Approval is already committed. Calendar failure cannot roll it back."""
        from google_calendar import CalendarError
        source = self.repository.get(meeting_id)
        follow_up = next((item for item in source.get("followUps", []) if item["id"] == follow_up_id), None)
        if follow_up is None:
            raise FollowUpNotFound()
        if follow_up["status"] != "approved":
            raise FollowUpConflict("Approve this follow-up in Synq before creating a Calendar event.")
        scheduled_id = follow_up["scheduledMeetingId"]
        meeting = self.repository.get(scheduled_id)
        if meeting.get("googleCalendar", {}).get("status") == "created":
            return meeting

        def persist(state):
            def change(current):
                # A concurrent successful retry always wins over a failed request.
                if current.get("googleCalendar", {}).get("status") == "created":
                    return current
                prior = current.get("googleCalendar", {})
                binding = {key: prior[key] for key in ("accountId", "timeZone") if key in prior}
                return validate_meeting({**current, "googleCalendar": {**state, **binding}})
            return self._update_retry(scheduled_id, change)

        state = dict(meeting.get("googleCalendar", {}))
        try:
            calendar = self.calendar_factory() if self.calendar_factory else None
            connection = calendar.connection() if calendar else None
            if connection is None:
                return persist({**state, "status": "not_connected", "error": "Synq meeting saved. Connect Google Calendar, then create its event."})
            if state.get("accountId") and state["accountId"] != connection["accountId"]:
                raise CalendarError("Reconnect the original Google account before retrying this event. This prevents duplicate events across accounts.")
            state = {"status": "pending", "accountId": connection["accountId"],
                     "timeZone": state.get("timeZone") or calendar.config["GOOGLE_CALENDAR_TIME_ZONE"]}
            # Persist organizer/timezone before any request with external side effects.
            def claim(current):
                prior = current.get("googleCalendar", {})
                if prior.get("status") == "created":
                    return current
                if prior.get("accountId") and prior["accountId"] != connection["accountId"]:
                    raise CalendarError("Another Google account owns this event attempt. Reconnect that account and retry.")
                return validate_meeting({**current, "googleCalendar": {**state, "timeZone": prior.get("timeZone") or state["timeZone"]}})
            meeting = self._update_retry(scheduled_id, claim)
            state = dict(meeting["googleCalendar"])
            if state["status"] == "created":
                return meeting
            metadata = calendar.ensure_event(meeting, source, connection, state["timeZone"])
            return persist({**state, **metadata, "status": "created"})
        except Exception as exc:
            message = str(exc) if isinstance(exc, CalendarError) else "Google Calendar could not be completed or saved. Your Synq meeting is saved. Retry Calendar creation."
            failed = {**state, "status": "failed", "error": message}
            # Never publish event metadata from an uncommitted/unconfirmed attempt.
            failed.pop("eventId", None)
            failed.pop("eventUrl", None)
            try:
                return persist(failed)
            except Exception:
                # Approval still succeeded. Return a clear partial-success result;
                # the existing approved source link makes retry possible on reload.
                return {**meeting, "googleCalendar": failed}

    def _update_retry(self, meeting_id, change):
        """Retry only side-effect-free changes against the latest Cosmos ETag."""
        for attempt in range(3):
            try:
                return self.repository.update(meeting_id, change)
            except MeetingWriteConflict:
                if attempt == 2:
                    raise

    def process(self, meeting_id: str) -> Meeting:
        def begin(current):
            transcript = current.get("transcript", [])
            if not isinstance(transcript, list) or not any(
                isinstance(line, dict) and isinstance(line.get("text"), str) and line["text"].strip()
                for line in transcript
            ):
                raise MeetingError("A saved, non-empty transcript is required for AI processing.")
            if current["aiStatus"] == "processing":
                raise AIProcessingConflict("This meeting is already being processed.")
            return {**current, "aiStatus": "processing"}

        started = self._update_retry(meeting_id, begin)
        context = processing_context(started)
        try:
            provider = self.ai_provider if self.ai_provider is not None else create_ai_provider()
            raw = provider.analyze(deepcopy(context))
            normalized = normalize_intelligence(raw, started)

            def finish(current):
                if current["aiStatus"] != "processing" or processing_context(current) != context:
                    raise AIProcessingConflict("Meeting context changed while processing. Please retry.")
                return merge_intelligence(current, normalized)

            return self._update_retry(meeting_id, finish)
        except Exception as exc:
            logging.exception("AI processing failed for meeting %s", meeting_id)
            def fail(current):
                if current["aiStatus"] == "processing":
                    current["aiStatus"] = "failed"
                return current

            try:
                self._update_retry(meeting_id, fail)
            except Exception:
                logging.error("Unable to persist AI failure state for meeting %s", meeting_id)
            # No fake results, and no raw provider errors/credentials in the API.
            raise AIProcessingFailed() from exc

    def create_jira_issue(self, meeting_id: str, action_item_id: str, jira: Any) -> tuple[dict[str, Any], bool]:
        """Create a Jira issue once per action item and persist its key and URL.

        Returns (action item, created). If the item already has jiraIssueKey,
        Jira is not called and the stored item is returned with created=False.
        """
        item = self._action_item(self.repository.get(meeting_id), action_item_id)
        if item.get("jiraIssueKey"):
            return deepcopy(item), False

        try:
            assignee = item.get("assignee", {})
            assignee_id = assignee.get("id")

            account_id = jira.get_account_id(assignee_id)

            issue = jira.create_task(
                item["text"],
                assignee_account_id=account_id
            )
        except Exception as exc:
            raise JiraCreateFailed() from exc

        outcome: dict[str, Any] = {}

        def change(current: Meeting) -> Meeting:
            # Re-find the item in the latest stored record so other edits
            # (status, other items) are not overwritten by a stale copy.
            target = self._action_item(current, action_item_id)
            if target.get("jiraIssueKey"):
                outcome["item"], outcome["created"] = deepcopy(target), False
                return current
            target["jiraIssueKey"] = issue["key"]
            target["jiraIssueUrl"] = issue["url"]
            outcome["item"], outcome["created"] = deepcopy(target), True
            return validate_meeting(current)

        self._update_retry(meeting_id, change)
        return outcome["item"], outcome["created"]

    @staticmethod
    def _action_item(meeting: Meeting, action_item_id: str) -> dict[str, Any]:
        for item in meeting.get("actionItems", []):
            if item["id"] == action_item_id:
                return item
        raise ActionItemNotFound()

    @staticmethod
    def _suggested_follow_up(meeting: Meeting, follow_up_id: str) -> dict[str, Any]:
        for follow_up in meeting.get("followUps", []):
            if follow_up["id"] == follow_up_id:
                if follow_up["status"] != "suggested":
                    raise FollowUpConflict("Follow-up is no longer suggested.")
                return follow_up
        raise FollowUpNotFound()

    def join_meeting(self, payload):
        return self.transcription.start(payload)

    def end_transcription(self, meeting_id):
        return self.transcription.end(meeting_id)

    def poll_transcriptions(self):
        self.transcription.poll_pending()
