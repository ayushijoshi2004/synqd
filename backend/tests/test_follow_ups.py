"""Follow-up state, edited approval, and concurrent resolution regression tests."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import azure.functions as func

import support  # noqa: F401  (must precede function_app)
import function_app
from meeting_errors import FollowUpConflict, FollowUpNotFound, MeetingAlreadyExists, MeetingError, MeetingNotFound
from meeting_repository import InMemoryMeetingRepository
from meeting_service import MeetingService
from seed_data import load_seed_meetings


class FollowUpTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryMeetingRepository(load_seed_meetings())
        self.service = MeetingService(self.repository)

    def proposal(self, meeting_id="m1", follow_up_id="f1"):
        return next(item for item in self.service.get(meeting_id)["followUps"] if item["id"] == follow_up_id)

    def test_seed_owns_all_demo_suggestions(self):
        follow_ups = [item for meeting in self.service.list() for item in meeting.get("followUps", [])]
        self.assertEqual({item["id"] for item in follow_ups}, {"f1", "f2", "f3"})
        self.assertEqual({item["status"] for item in follow_ups}, {"suggested"})
        for item in follow_ups:
            self.assertIn(item, self.service.get(item["sourceMeetingId"])["followUps"])

    def test_dismiss_survives_new_service_using_same_repository(self):
        count = len(self.service.list())
        self.service.dismiss_follow_up("m1", "f1")
        reread = MeetingService(self.repository).list()
        self.assertEqual(len(reread), count)
        source = next(meeting for meeting in reread if meeting["id"] == "m1")
        self.assertEqual(source["followUps"][0]["status"], "dismissed")
        self.assertEqual(source["followUps"][1]["status"], "suggested")
        self.assertNotIn("scheduledMeetingId", source["followUps"][0])

    def test_approve_saves_edited_values_and_scheduled_link(self):
        edits = {
            "title": "Edited Growth review", "date": "2026-11-04",
            "startTime": "16:15", "endTime": "17:45", "project": "Review project",
            "team": "QA", "agenda": "Edited agenda",
            "participants": [{"id": "reviewer", "name": "Reviewer", "color": "#2f6f5e"}],
        }
        count = len(self.service.list())
        result = self.service.approve_follow_up("m3", "f2", edits)
        meeting = result["meeting"]
        proposal = self.proposal("m3", "f2")
        self.assertEqual(len(self.service.list()), count + 1)
        for field, value in edits.items():
            self.assertEqual(meeting[field], value)
            self.assertEqual(proposal[field], value)
        self.assertEqual((meeting["status"], meeting["aiStatus"]), ("scheduled", "unprocessed"))
        self.assertEqual(proposal["status"], "approved")
        self.assertEqual(proposal["scheduledMeetingId"], meeting["id"])
        self.assertEqual(proposal["sourceMeetingId"], "m3")
        self.assertEqual(result["sourceMeeting"], self.service.get("m3"))
        reread = MeetingService(self.repository)
        self.assertEqual(reread.get(meeting["id"]), meeting)
        self.assertEqual(reread.get("m3"), result["sourceMeeting"])

    def test_approval_without_edits_uses_existing_suggestion(self):
        original = self.proposal()
        result = self.service.approve_follow_up("m1", "f1", {})
        self.assertEqual(result["meeting"]["title"], original["title"])
        self.assertEqual(result["meeting"]["participants"], original["participants"])

    def test_duplicate_and_cross_resolution_rejected(self):
        for first in ("approve", "dismiss"):
            with self.subTest(first=first):
                self.setUp()
                if first == "approve":
                    self.service.approve_follow_up("m1", "f1", {})
                else:
                    self.service.dismiss_follow_up("m1", "f1")
                before = self.service.list()
                with self.assertRaises(FollowUpConflict):
                    self.service.approve_follow_up("m1", "f1", {})
                with self.assertRaises(FollowUpConflict):
                    self.service.dismiss_follow_up("m1", "f1")
                self.assertEqual(self.service.list(), before)

    def test_invalid_edits_leave_both_records_unchanged(self):
        for edits in (None, [], {"title": ""}, {"endTime": "01:00"}, {"participants": []}, {"id": "new"}, {"status": "ended"}, {"aiStatus": "processed"}, {"sourceMeetingId": "m3"}):
            with self.subTest(edits=edits), self.assertRaises(MeetingError):
                before = self.service.list()
                self.service.approve_follow_up("m1", "f1", edits)
            self.assertEqual(self.service.list(), before)

    def test_create_failure_does_not_mark_source_approved(self):
        before = self.service.list()
        with patch.object(self.repository, "create", side_effect=MeetingAlreadyExists()):
            with self.assertRaises(MeetingAlreadyExists):
                self.service.approve_follow_up("m1", "f1", {})
        self.assertEqual(self.service.list(), before)

    def test_missing_source_and_follow_up(self):
        for resolve in (lambda mid, fid: self.service.approve_follow_up(mid, fid, {}), self.service.dismiss_follow_up):
            with self.assertRaises(MeetingNotFound):
                resolve("missing", "f1")
            with self.assertRaises(FollowUpNotFound):
                resolve("m1", "missing")
            with self.assertRaises(FollowUpNotFound):
                resolve("m3", "f1")

    def test_parallel_approval_creates_exactly_one_meeting(self):
        before = len(self.service.list())

        def approve(_):
            try:
                return self.service.approve_follow_up("m1", "f1", {})
            except FollowUpConflict:
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(approve, range(8)))
        self.assertEqual(sum(item is not None for item in results), 1)
        self.assertEqual(len(self.service.list()), before + 1)

    def test_parallel_approve_and_dismiss_have_one_winner(self):
        before = len(self.service.list())

        def resolve(action):
            try:
                if action == "approve":
                    self.service.approve_follow_up("m1", "f1", {})
                else:
                    self.service.dismiss_follow_up("m1", "f1")
                return action
            except FollowUpConflict:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            winners = [result for result in pool.map(resolve, ("approve", "dismiss")) if result]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(self.service.list()), before + (winners[0] == "approve"))

    def test_stale_demo_append_cannot_reset_resolved_state(self):
        stale = self.service.get("m1")["followUps"]
        self.service.dismiss_follow_up("m1", "f1")
        before = self.service.list()
        with self.assertRaises(FollowUpConflict):
            self.service.patch("m1", {"followUps": stale})
        self.assertEqual(self.service.list(), before)
        current = self.service.get("m1")["followUps"]
        new = {**deepcopy(current[1]), "id": "new-demo"}
        updated = self.service.patch("m1", {"followUps": [*current, new]})
        self.assertEqual(updated["followUps"][0]["status"], "dismissed")
        self.assertEqual(updated["followUps"][-1], new)

    def test_invalid_follow_up_shapes_are_rejected(self):
        proposal = self.proposal()
        for value in (None, {}, [None], [proposal, proposal], [{**proposal, "status": "scheduled"}], [{**proposal, "sourceMeetingId": "m3"}], [{**proposal, "endTime": "01:00"}], [{**proposal, "status": "approved"}], [{**proposal, "scheduledMeetingId": "new"}]):
            with self.subTest(value=value), self.assertRaises(MeetingError):
                self.service.patch("m1", {"followUps": value})


class FollowUpHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse registered functions without re-indexing the FunctionApp.
        cls.functions = {
            name: getattr(function_app, name)._function.get_user_function()
            for name in ("approve_follow_up", "dismiss_follow_up")
        }

    def setUp(self):
        service = MeetingService(InMemoryMeetingRepository(load_seed_meetings()))
        self.service_patch = patch.object(function_app, "meetings", service)
        self.service_patch.start()
        self.addCleanup(self.service_patch.stop)

    def request(self, action, meeting_id="m1", follow_up_id="f1", body=b"{}"):
        req = func.HttpRequest(
            method="POST", url=f"http://localhost/api/meetings/{meeting_id}/follow-ups/{follow_up_id}/{action}",
            body=body, route_params={"meeting_id": meeting_id, "follow_up_id": follow_up_id},
        )
        response = self.functions[f"{action}_follow_up"](req)
        self.assertEqual(response.mimetype, "application/json")
        return response.status_code, json.loads(response.get_body())

    def test_success_and_conflict_responses(self):
        status, body = self.request("approve", body=b'{"title":"Reviewed"}')
        self.assertEqual(status, 200)
        self.assertEqual(body["meeting"]["title"], "Reviewed")
        self.assertEqual(body["sourceMeeting"]["followUps"][0]["status"], "approved")
        self.assertEqual(self.request("approve")[0], 409)
        self.assertEqual(self.request("dismiss")[0], 409)
        status, body = self.request("dismiss", "m3", "f2")
        self.assertEqual(status, 200)
        self.assertEqual(body["followUps"][0]["status"], "dismissed")

    def test_404_and_400_responses(self):
        for action in ("approve", "dismiss"):
            self.assertEqual(self.request(action, meeting_id="missing")[0], 404)
            self.assertEqual(self.request(action, follow_up_id="missing")[0], 404)
        self.assertEqual(self.request("approve", body=b"{invalid")[0], 400)
        self.assertEqual(self.request("approve", body=b'{"status":"ended"}')[0], 400)
