"""Jira persistence and duplicate prevention. Jira is always mocked."""

import json
import unittest
from unittest.mock import MagicMock, patch

import support  # noqa: F401  (must precede function_app)
import azure.functions as func

import function_app
from meeting_errors import ActionItemNotFound, JiraCreateFailed, MeetingNotFound
from meeting_repository import InMemoryMeetingRepository
from meeting_service import MeetingService
from seed_data import load_seed_meetings

URL = "https://synq-team-hackathon.atlassian.net/browse/KAN-8"


def fake_jira(key="KAN-8"):
    jira = MagicMock()
    jira.create_task.return_value = {"key": key, "url": URL.replace("KAN-8", key)}
    return jira


class JiraServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryMeetingRepository(load_seed_meetings())
        self.service = MeetingService(self.repository)

    def task(self, task_id="t1"):
        return next(t for t in self.service.get("m1")["actionItems"] if t["id"] == task_id)

    def test_creation_stores_key_and_url_on_the_correct_item(self):
        jira = fake_jira()
        item, created = self.service.create_jira_issue("m1", "t1", jira)
        self.assertTrue(created)
        self.assertEqual((item["jiraIssueKey"], item["jiraIssueUrl"]), ("KAN-8", URL))
        jira.create_task.assert_called_once()
        self.assertEqual(jira.create_task.call_args.args, ("Fix declined-card retry bug",))
        self.assertIn("assignee_account_id", jira.create_task.call_args.kwargs)
        # The stored meeting carries the metadata, and no other item does.
        self.assertEqual(self.task("t1")["jiraIssueKey"], "KAN-8")
        self.assertEqual(self.task("t1")["jiraIssueUrl"], URL)
        others = [t for t in self.service.get("m1")["actionItems"] if t["id"] != "t1"]
        self.assertTrue(others)
        self.assertTrue(all("jiraIssueKey" not in t for t in others))

    def test_creation_does_not_complete_or_change_the_task(self):
        before = self.task("t2")
        self.service.create_jira_issue("m1", "t2", fake_jira("KAN-9"))
        after = self.task("t2")
        self.assertEqual(after["status"], before["status"])
        self.assertEqual({k: v for k, v in after.items() if not k.startswith("jira")}, before)

    def test_metadata_survives_a_new_service_on_the_same_storage(self):
        self.service.create_jira_issue("m1", "t1", fake_jira())
        reread = next(m for m in MeetingService(self.repository).list() if m["id"] == "m1")
        self.assertEqual(next(t for t in reread["actionItems"] if t["id"] == "t1")["jiraIssueKey"], "KAN-8")

    def test_repeat_request_does_not_call_jira_again(self):
        jira = fake_jira()
        first, created_first = self.service.create_jira_issue("m1", "t1", jira)
        second, created_second = self.service.create_jira_issue("m1", "t1", jira)
        third, _ = self.service.create_jira_issue("m1", "t1", jira)
        self.assertEqual((created_first, created_second), (True, False))
        self.assertEqual(first, second)
        self.assertEqual(second, third)
        self.assertEqual(jira.create_task.call_count, 1)

    def test_item_with_existing_metadata_never_reaches_jira(self):
        self.service.create_jira_issue("m1", "t1", fake_jira("KAN-3"))
        jira = fake_jira("KAN-99")
        item, created = self.service.create_jira_issue("m1", "t1", jira)
        self.assertFalse(created)
        self.assertEqual(item["jiraIssueKey"], "KAN-3")
        jira.create_task.assert_not_called()

    def test_unknown_meeting_and_item_are_not_found_and_skip_jira(self):
        jira = fake_jira()
        with self.assertRaises(MeetingNotFound):
            self.service.create_jira_issue("missing", "t1", jira)
        with self.assertRaises(ActionItemNotFound):
            self.service.create_jira_issue("m1", "missing", jira)
        with self.assertRaises(ActionItemNotFound):
            self.service.create_jira_issue("m3", "t1", jira)  # meeting with no action items
        jira.create_task.assert_not_called()

    def test_jira_failure_saves_nothing(self):
        jira = MagicMock()
        jira.create_task.side_effect = RuntimeError("boom")
        with self.assertRaises(JiraCreateFailed):
            self.service.create_jira_issue("m1", "t1", jira)
        self.assertNotIn("jiraIssueKey", self.task("t1"))

    def test_meeting_crud_and_follow_ups_still_work_with_jira_metadata(self):
        self.service.create_jira_issue("m1", "t1", fake_jira())
        self.assertEqual(self.service.patch("m1", {"title": "Renamed"})["title"], "Renamed")
        self.assertEqual(self.task("t1")["jiraIssueKey"], "KAN-8")
        self.assertEqual(self.service.dismiss_follow_up("m1", "f1")["followUps"][0]["status"], "dismissed")
        result = self.service.approve_follow_up("m1", "f3", {})
        self.assertEqual(result["sourceMeeting"]["followUps"][1]["status"], "approved")
        self.assertEqual(self.task("t1")["jiraIssueUrl"], URL)
        created = self.service.create({
            "title": "New", "date": "2026-10-10", "startTime": "10:00", "endTime": "11:00",
            "participants": [{"id": "a", "name": "A", "color": "#000000"}],
        })
        self.service.delete(created["id"])
        with self.assertRaises(MeetingNotFound):
            self.service.get(created["id"])

    def test_patch_cannot_save_malformed_jira_metadata(self):
        items = self.service.get("m1")["actionItems"]
        items[0]["jiraIssueKey"] = 7
        with self.assertRaises(Exception):
            self.service.patch("m1", {"actionItems": items})
        self.assertNotIn("jiraIssueKey", self.task("t1"))


class JiraRouteTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryMeetingRepository(load_seed_meetings())
        self.service = MeetingService(self.repository)
        self.jira = fake_jira()
        # Same lookup test_follow_ups uses; avoids repeated app.get_functions() calls.
        self.route = function_app.create_jira_for_action_item._function.get_user_function()
        for target, value in (("meetings", self.service), ("_jira_service", self.jira)):
            patcher = patch.object(function_app, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def post(self, meeting_id="m1", task_id="t1"):
        request = func.HttpRequest(
            method="POST", body=b"",
            url=f"http://localhost/api/meetings/{meeting_id}/action-items/{task_id}/jira",
            route_params={"meeting_id": meeting_id, "action_item_id": task_id},
        )
        response = self.route(request)
        return response.status_code, json.loads(response.get_body())

    def test_first_post_creates_then_repeats_return_existing(self):
        status, body = self.post()
        self.assertEqual(status, 201)
        self.assertEqual((body["id"], body["jiraIssueKey"], body["jiraIssueUrl"]), ("t1", "KAN-8", URL))
        for _ in range(3):
            status, again = self.post()
            self.assertEqual(status, 200)
            self.assertEqual(again, body)
        self.assertEqual(self.jira.create_task.call_count, 1)

    def test_get_meeting_after_post_returns_metadata(self):
        self.post()
        stored = next(t for t in self.service.get("m1")["actionItems"] if t["id"] == "t1")
        self.assertEqual(stored["jiraIssueKey"], "KAN-8")

    def test_errors_map_to_json_status_codes(self):
        self.assertEqual(self.post("missing", "t1")[0], 404)
        self.assertEqual(self.post("m1", "missing")[0], 404)
        self.jira.create_task.side_effect = RuntimeError("secret detail")
        status, body = self.post()
        self.assertEqual(status, 502)
        self.assertEqual(body["error"]["code"], "jira_error")
        self.assertNotIn("secret", json.dumps(body))


if __name__ == "__main__":
    unittest.main()
