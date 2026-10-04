"""Run from backend/: python -m unittest discover -s tests -v."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import unittest
from uuid import UUID

import azure.functions as func

import support  # noqa: F401  (must precede function_app)
import function_app
from api_http import read_body, respond
from meeting_errors import MeetingAlreadyExists, MeetingError, MeetingNotFound
from meeting_model import AI_STATUSES, CORE_FIELDS, STATUSES
from meeting_repository import InMemoryMeetingRepository
from meeting_service import MeetingService
from seed_data import load_seed_meetings


def payload(**overrides):
    return {
        "title": "Local CRUD review",
        "date": "2026-10-10",
        "startTime": "10:15",
        "endTime": "11:00",
        "participants": [{"id": "maya", "name": "Maya Chen", "color": "#c96f4a"}],
        **overrides,
    }


class MeetingServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryMeetingRepository(load_seed_meetings())
        self.service = MeetingService(self.repository)

    def test_seed_details_match_supported_frontend_fields(self):
        records = self.service.list()
        self.assertEqual({item["id"] for item in records}, {"m1", "m3", "m4", "m5"})
        atlas = self.service.get("m1")
        self.assertEqual(atlas["status"], "ended")
        self.assertEqual(atlas["aiStatus"], "processed")
        self.assertEqual(len(atlas["actionItems"]), 5)
        self.assertEqual(atlas["actionItems"][1]["status"], "in_progress")

    def test_create_defaults_and_generated_id(self):
        created = self.service.create(payload())
        UUID(created["id"])
        self.assertEqual(set(created), CORE_FIELDS)
        self.assertEqual(created["status"], "scheduled")
        self.assertEqual(created["aiStatus"], "unprocessed")
        for field in ("project", "team", "agenda", "preview"):
            self.assertEqual(created[field], "")
        self.assertEqual(self.service.get(created["id"]), created)

    def test_supplied_id_and_duplicate_conflict(self):
        created = self.service.create(payload(id="demo-custom-id"))
        self.assertEqual(created["id"], "demo-custom-id")
        with self.assertRaises(MeetingAlreadyExists):
            self.service.create(payload(id="demo-custom-id"))

    def test_post_requires_title_date_times_and_participants(self):
        for field in ("title", "date", "startTime", "endTime", "participants"):
            invalid = payload()
            del invalid[field]
            with self.subTest(field=field), self.assertRaises(MeetingError):
                self.service.create(invalid)

    def test_invalid_shapes_dates_times_and_participants(self):
        invalid_values = [
            None, [], "not an object", payload(title=" "), payload(title=2),
            payload(date="2026-02-30"), payload(date="10/10/2026"),
            payload(startTime="24:00"), payload(endTime="10:15"),
            payload(endTime="09:30"), payload(participants=[]),
            payload(participants="Maya"), payload(participants=[{"name": "Maya"}]),
            payload(participants=payload()["participants"] * 2), payload(id=None),
            payload(id="../invalid"), payload(extraField="unsupported"),
        ]
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(MeetingError):
                self.service.create(value)

    def test_all_lifecycle_and_ai_status_values_are_independent(self):
        for status in STATUSES:
            for ai_status in AI_STATUSES:
                created = self.service.create(payload(status=status, aiStatus=ai_status))
                self.assertEqual(created["status"], status)
                self.assertEqual(created["aiStatus"], ai_status)

    def test_invalid_statuses_rejected_on_post_and_patch(self):
        for field in ("status", "aiStatus"):
            for invalid in ("Processed", "invalid", None, [], {}):
                with self.subTest(field=field, invalid=invalid):
                    with self.assertRaises(MeetingError):
                        self.service.create(payload(**{field: invalid}))
                    before = self.service.get("m1")
                    with self.assertRaises(MeetingError):
                        self.service.patch("m1", {field: invalid})
                    self.assertEqual(self.service.get("m1"), before)

    def test_no_backend_eight_participant_limit(self):
        people = [{"id": f"p{i}", "name": f"Person {i}", "color": "#2f6f5e"} for i in range(12)]
        created = self.service.create(payload(participants=people))
        self.assertEqual(len(created["participants"]), 12)

    def test_patch_updates_only_supplied_fields(self):
        before = self.service.get("m1")
        changes = {"title": "Updated title", "date": "2026-11-01", "startTime": "14:10", "endTime": "15:05", "status": "scheduled", "aiStatus": "unprocessed"}
        updated = self.service.patch("m1", changes)
        self.assertEqual(updated, {**before, **changes})

    def test_patch_rejects_id_and_unknown_fields_without_partial_write(self):
        before = self.service.get("m1")
        for patch in ({}, {"id": "new-id"}, {"title": "Bad write", "unknown": 1}, {"endTime": "09:00"}):
            with self.subTest(patch=patch), self.assertRaises(MeetingError):
                self.service.patch("m1", patch)
            self.assertEqual(self.service.get("m1"), before)

    def test_optional_detail_roundtrip_and_whole_field_patch(self):
        original = self.service.get("m1")
        original["id"] = "detail-copy"
        for follow_up in original.get("followUps", []):
            follow_up["sourceMeetingId"] = original["id"]
        created = self.service.create(original)
        self.assertEqual(created, original)
        updated = self.service.patch("detail-copy", {"actionItems": [], "agenda": "New agenda"})
        self.assertEqual(updated["actionItems"], [])
        self.assertEqual(updated["summary"], original["summary"])
        self.assertEqual(updated["agendaEntries"], original["agendaEntries"])

    def test_invalid_nested_detail_shapes_are_rejected(self):
        bad_details = [
            {"agendaEntries": [{"title": "QA", "timestamp": "", "completed": "yes"}]},
            {"summary": {"points": []}}, {"transcript": ["text"]},
            {"decisions": [{}]}, {"actionItems": [{"status": "Processed"}]},
            {"projectOverview": []}, {"assistant": {"scopeLabel": "demo", "suggestions": 3}},
        ]
        for invalid in bad_details:
            with self.subTest(invalid=invalid), self.assertRaises(MeetingError):
                self.service.create(payload(**invalid))

    def test_jira_metadata_does_not_change_task_status(self):
        items = self.service.get("m1")["actionItems"]
        items[0]["jiraIssueKey"] = "DEMO-123"
        updated = self.service.patch("m1", {"actionItems": items})
        self.assertEqual(updated["actionItems"][0]["status"], "todo")

    def test_get_patch_delete_unknown_ids(self):
        operations = (lambda: self.service.get("missing"), lambda: self.service.patch("missing", {"title": "Changed"}), lambda: self.service.delete("missing"))
        for operation in operations:
            with self.assertRaises(MeetingNotFound):
                operation()

    def test_delete_removes_record(self):
        created = self.service.create(payload())
        self.assertEqual(self.service.delete(created["id"]), {"id": created["id"], "deleted": True})
        with self.assertRaises(MeetingNotFound):
            self.service.get(created["id"])
        self.assertNotIn(created["id"], [item["id"] for item in self.service.list()])

    def test_repository_copies_inputs_and_outputs(self):
        incoming = payload()
        created = self.service.create(incoming)
        expected = deepcopy(created)
        incoming["participants"][0]["name"] = "Modified input"
        created["participants"][0]["name"] = "Modified output"
        listed = self.service.list()
        listed[-1]["title"] = "Modified list"
        self.assertEqual(self.service.get(expected["id"]), expected)

    def test_parallel_patches_do_not_lose_unsupplied_fields(self):
        created = self.service.create(payload())
        changes = [{"title": "Parallel"}, {"project": "Atlas Launch"}, {"team": "QA"}, {"agenda": "Discuss API"}]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda patch: self.service.patch(created["id"], patch), changes))
        result = self.service.get(created["id"])
        for patch in changes:
            for key, value in patch.items():
                self.assertEqual(result[key], value)


class HttpBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.functions = {function.get_function_name(): function.get_user_function() for function in function_app.app.get_functions()}

    def test_health_is_preserved(self):
        request = func.HttpRequest(method="GET", url="http://localhost/api/health", body=b"")
        response = self.functions["health"](request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.get_body()), {"status": "working"})
        self.assertEqual(response.mimetype, "application/json")

    def test_registered_routes(self):
        self.assertEqual(set(self.functions), {"health", "list_meetings", "create_meeting", "get_meeting", "patch_meeting", "delete_meeting", "dismiss_follow_up", "approve_follow_up", "jira_test", "create_jira_for_action_item", "process_meeting", "ask_meeting", "retry_follow_up_calendar", "google_calendar_status", "google_calendar_authorize", "google_calendar_callback", "join_meeting", "get_meeting_transcript", "end_transcription", "poll_transcriptions"})

    def test_json_error_and_status_mapping(self):
        request = func.HttpRequest(method="POST", url="http://localhost/api/meetings", body=b"{broken")
        invalid = respond(lambda: read_body(request))
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(json.loads(invalid.get_body())["error"]["code"], "invalid_meeting")
        service = MeetingService(InMemoryMeetingRepository())
        missing = respond(lambda: service.get("missing"))
        self.assertEqual(missing.status_code, 404)
        service.create(payload(id="duplicate"))
        conflict = respond(lambda: service.create(payload(id="duplicate")))
        self.assertEqual(conflict.status_code, 409)

    def test_creation_returns_json_and_location(self):
        service = MeetingService(InMemoryMeetingRepository())
        result = respond(lambda: service.create(payload()), created=True)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.mimetype, "application/json")
        meeting = json.loads(result.get_body())
        self.assertEqual(result.headers["Location"], f"/api/meetings/{meeting['id']}")


if __name__ == "__main__":
    unittest.main()
