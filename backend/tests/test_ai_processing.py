"""Deterministic processing tests. No Gemini, Cosmos, or Jira network calls."""

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

import support  # noqa: F401
import azure.functions as func
import requests
import function_app
from ai_provider import AIProviderError, create_ai_provider
from ai_schema import INTELLIGENCE_SCHEMA
from gemini_provider import GeminiProvider
from meeting_errors import AIProcessingConflict, AIProcessingFailed, MeetingError, MeetingNotFound, MeetingWriteConflict
from meeting_repository import InMemoryMeetingRepository
from meeting_service import MeetingService

MAYA = {"id": "maya", "name": "Maya Chen", "color": "#c96f4a"}
ALEX = {"id": "alex", "name": "Alex Rivera", "color": "#3f7cac"}
LINES = [
    "QA regression checks are complete and checkout tests passed. We will release on October 9.",
    "I will update the release checklist by Friday. We have not decided who will own the support rota.",
    "We should meet again to review support coverage.",
]


def evidence(index):
    return [{"entryIndex": index, "quote": LINES[index]}]


def source():
    return {
        "id": "ai-test", "title": "Launch review", "date": "2026-10-07",
        "startTime": "10:00", "endTime": "11:00", "project": "Atlas Launch", "team": "QA",
        "participants": [MAYA, ALEX], "agenda": "QA status\nBudget\nLaunch timeline",
        "status": "ended", "aiStatus": "unprocessed", "preview": "Original preview",
        "transcript": [
            {"timestamp": "00:10", "speaker": MAYA, "text": LINES[0]},
            {"timestamp": "01:20", "speaker": ALEX, "text": LINES[1]},
            {"timestamp": "", "speaker": MAYA, "text": LINES[2]},
        ],
        "agendaEntries": [{"title": title, "timestamp": "", "completed": False} for title in ("QA status", "Budget", "Launch timeline")],
        "summary": {"beforeHighlight": "Previously saved summary", "highlight": "", "afterHighlight": "", "points": []},
        "actionItems": [{"id": "existing", "text": "Existing task", "due": "", "status": "done", "assignee": MAYA,
                         "jiraIssueKey": "KAN-50", "jiraIssueUrl": "https://jira.example.invalid/browse/KAN-50"}],
        "decisions": [], "followUps": [],
    }


def intelligence():
    return {
        "summary": {"beforeHighlight": "QA passed. The team agreed to release on October 9.", "highlight": "", "afterHighlight": "", "points": ["Alex will update the checklist.", "Support ownership remains open."]},
        "decisions": [{"text": "Release on October 9", "participantId": "maya", "note": "", "evidence": evidence(0)}],
        "actionItems": [{"text": "Update the release checklist", "assigneeId": "alex", "due": "Friday", "status": "todo", "evidence": evidence(1)}],
        "unresolvedItems": [{"text": "Who will own the support rota?", "evidence": evidence(1)}],
        "followUps": [{"title": "Review support coverage", "date": "", "startTime": "", "endTime": "", "participantIds": [], "agenda": "Review support coverage", "status": "suggested", "evidence": evidence(2)}],
        "agendaEntries": [
            {"agendaIndex": 0, "title": "QA status", "completed": True, "evidence": evidence(0)},
            {"agendaIndex": 1, "title": "Budget", "completed": False, "evidence": []},
            {"agendaIndex": 2, "title": "Launch timeline", "completed": True, "evidence": evidence(0)},
        ],
    }


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryMeetingRepository([source()])
        self.provider = Mock()
        self.provider.analyze.return_value = intelligence()
        self.service = MeetingService(self.repo, self.provider)
        no_network = patch("requests.sessions.Session.request", side_effect=AssertionError("Network forbidden in tests"))
        no_network.start()
        self.addCleanup(no_network.stop)

    def test_success_persists_every_intelligence_field_and_preserves_metadata(self):
        before = self.service.get("ai-test")
        def analyze(context):
            self.assertEqual(self.service.get("ai-test")["aiStatus"], "processing")
            self.assertEqual(self.service.get("ai-test")["summary"], before["summary"])
            self.assertEqual(context["transcript"], before["transcript"])
            self.assertNotIn("actionItems", context)
            self.assertNotIn("jiraIssueKey", json.dumps(context))
            return intelligence()
        self.provider.analyze.side_effect = analyze
        after = self.service.process("ai-test")
        self.assertEqual(after["aiStatus"], "processed")
        self.assertEqual(after["summary"], intelligence()["summary"])
        self.assertEqual(after["decisions"][0]["text"], "Release on October 9")
        self.assertEqual(after["decisions"][0]["participant"], MAYA)
        action = after["actionItems"][-1]
        self.assertEqual((action["status"], action["assignee"], action["due"]), ("todo", ALEX, "Friday"))
        self.assertFalse(any(key.startswith("jira") for key in action))
        self.assertEqual(after["unresolvedItems"], ["Who will own the support rota?"])
        proposal = after["followUps"][0]
        self.assertEqual(proposal["status"], "suggested")
        self.assertEqual(proposal["sourceMeetingId"], "ai-test")
        self.assertEqual((proposal["date"], proposal["startTime"], proposal["endTime"], proposal["participants"]), ("", "", "", []))
        self.assertNotIn("scheduledMeetingId", proposal)
        self.assertEqual(len(self.service.list()), 1)
        for item in (action, proposal, after["decisions"][0]):
            UUID(item["id"])
        self.assertEqual([a["title"] for a in after["agendaEntries"]], [a["title"] for a in before["agendaEntries"]])
        self.assertEqual([a["completed"] for a in after["agendaEntries"]], [True, False, True])
        self.assertEqual(after["agendaEntries"][0]["timestamp"], "00:10")
        for field in ("transcript", "participants", "id", "title", "date", "startTime", "endTime", "project", "team", "status", "preview", "agenda"):
            self.assertEqual(after[field], before[field])
        self.assertEqual(after["actionItems"][0], before["actionItems"][0])
        self.assertEqual(MeetingService(self.repo).get("ai-test"), after)

    def test_unknown_owners_are_null_not_invented_participants(self):
        result = intelligence()
        result["actionItems"][0]["assigneeId"] = None
        result["decisions"][0]["participantId"] = None
        self.provider.analyze.return_value = result
        after = self.service.process("ai-test")
        self.assertIsNone(after["actionItems"][-1]["assignee"])
        self.assertIsNone(after["decisions"][0]["participant"])
        self.assertEqual(after["participants"], source()["participants"])

    def test_empty_extraction_arrays_do_not_fabricate_items(self):
        self.repo.update("ai-test", lambda m: {**m, "decisions": [{"id": "old", "text": "Earlier analysis", "participant": None, "timestamp": "", "note": ""}]})
        result = intelligence()
        for field in ("decisions", "actionItems", "unresolvedItems", "followUps"):
            result[field] = []
        self.provider.analyze.return_value = result
        after = self.service.process("ai-test")
        for field in ("decisions", "unresolvedItems", "followUps"):
            self.assertEqual(after[field], [])
        self.assertEqual(after["actionItems"], source()["actionItems"])

    def test_missing_transcript_and_unknown_meeting_skip_provider(self):
        for transcript in ([], [{"timestamp": "", "speaker": MAYA, "text": " "}]):
            self.repo.update("ai-test", lambda m: {**m, "transcript": transcript})
            before = self.service.get("ai-test")
            with self.assertRaises(MeetingError): self.service.process("ai-test")
            self.assertEqual(self.service.get("ai-test"), before)
        with self.assertRaises(MeetingNotFound): self.service.process("missing")
        self.provider.analyze.assert_not_called()

    def test_duplicate_processing_is_rejected_before_provider(self):
        self.repo.update("ai-test", lambda m: {**m, "aiStatus": "processing"})
        with self.assertRaises(AIProcessingConflict): self.service.process("ai-test")
        self.provider.analyze.assert_not_called()

    def test_provider_failures_save_only_failed_status_and_allow_retry(self):
        for failure in (AIProviderError("quota"), requests.Timeout("timeout"), RuntimeError("secret-key")):
            with self.subTest(failure=type(failure).__name__):
                before = self.service.get("ai-test")
                self.provider.analyze.side_effect = failure
                with self.assertRaises(AIProcessingFailed) as error: self.service.process("ai-test")
                self.assertNotIn("secret-key", str(error.exception))
                self.assertEqual(self.service.get("ai-test"), {**before, "aiStatus": "failed"})
        self.provider.analyze.side_effect = None
        self.assertEqual(self.service.process("ai-test")["aiStatus"], "processed")

    def test_invalid_output_never_partially_updates_intelligence(self):
        cases = [None, [], "free prose", {}, {**intelligence(), "agendaProgress": []}]
        for field, replacement in (("summary", None), ("actionItems", None), ("followUps", {})):
            cases.append({**intelligence(), field: replacement})
        mutations = [
            ("actionItems", "jiraIssueKey", "FAKE-1"), ("actionItems", "jiraIssueUrl", "https://fake.invalid"),
            ("actionItems", "status", "done"), ("actionItems", "id", "user-id"),
            ("actionItems", "assigneeId", "invented-owner"),
            ("followUps", "status", "approved"), ("followUps", "scheduledMeetingId", "invented"),
            ("followUps", "date", "2050-01-01"), ("followUps", "startTime", "14:00"),
            ("agendaEntries", "title", "Invented topic"), ("agendaEntries", "agendaIndex", 50),
            ("agendaEntries", "agendaIndex", True), ("agendaEntries", "timestamp", "invented"),
            ("agendaEntries", "completed", "true"), ("agendaEntries", "evidence", [{"entryIndex": 0, "quote": "QA"}]),
            ("decisions", "evidence", [{"entryIndex": 0, "quote": "We approved a billion-dollar budget"}]),
        ]
        for field, key, value in mutations:
            output = intelligence()
            output[field][0][key] = value
            cases.append(output)
        missing = intelligence(); missing["agendaEntries"].pop(); cases.append(missing)
        duplicated = intelligence(); duplicated["agendaEntries"][1] = deepcopy(duplicated["agendaEntries"][0]); cases.append(duplicated)
        for output in cases:
            with self.subTest(output=output):
                before = self.service.get("ai-test")
                self.provider.analyze.return_value = output
                with self.assertRaises(AIProcessingFailed): self.service.process("ai-test")
                self.assertEqual(self.service.get("ai-test"), {**before, "aiStatus": "failed"})

    def test_unsupported_due_date_is_removed_without_losing_task(self):
        output = intelligence()
        output["actionItems"][0]["due"] = "2050-01-01"
        self.provider.analyze.return_value = output
        result = self.service.process("ai-test")
        task = next(item for item in result["actionItems"] if item["text"] == "Update the release checklist")
        self.assertEqual(task["due"], "")

    def test_unavailable_timestamps_preserve_existing_values(self):
        def edit(m):
            for line in m["transcript"]: line["timestamp"] = ""
            m["agendaEntries"][0]["timestamp"] = "saved-reference"
            return m
        self.repo.update("ai-test", edit)
        after = self.service.process("ai-test")
        self.assertEqual(after["agendaEntries"][0]["timestamp"], "saved-reference")
        self.assertEqual(after["agendaEntries"][2]["timestamp"], "")
        self.assertEqual(after["decisions"][0]["timestamp"], "")

    def test_explicit_follow_up_timing_is_kept_without_assumed_end(self):
        quote = "Let's meet Friday at 2 PM to review support coverage."
        self.repo.update("ai-test", lambda m: {**m, "transcript": [*m["transcript"][:2], {"timestamp": "", "speaker": MAYA, "text": quote}]})
        result = intelligence()
        result["followUps"][0].update(date="2026-10-09", startTime="14:00", evidence=[{"entryIndex": 2, "quote": quote}])
        self.provider.analyze.return_value = result
        proposal = self.service.process("ai-test")["followUps"][0]
        self.assertEqual((proposal["date"], proposal["startTime"], proposal["endTime"]), ("2026-10-09", "14:00", ""))

    def test_weekday_evidence_cannot_justify_an_arbitrary_future_date(self):
        quote = "Let's meet Friday at 2 PM to review support coverage."
        self.repo.update("ai-test", lambda m: {**m, "transcript": [*m["transcript"][:2], {"timestamp": "", "speaker": MAYA, "text": quote}]})
        result = intelligence()
        result["followUps"][0].update(date="2050-01-07", startTime="14:00", evidence=[{"entryIndex": 2, "quote": quote}])
        self.provider.analyze.return_value = result
        with self.assertRaises(AIProcessingFailed): self.service.process("ai-test")
        self.assertEqual(self.service.get("ai-test")["followUps"], [])

    def test_ai_tasks_use_existing_jira_flow_and_reprocessing_preserves_it(self):
        first = self.service.process("ai-test")
        task_id = first["actionItems"][-1]["id"]
        jira = Mock()
        jira.create_task.return_value = {"key": "KAN-51", "url": "https://jira.example.invalid/browse/KAN-51"}
        linked, created = self.service.create_jira_issue("ai-test", task_id, jira)
        self.assertTrue(created)
        self.assertEqual(linked["status"], "todo")
        jira.create_task.assert_called_once()
        self.assertEqual(jira.create_task.call_args.args, ("Update the release checklist",))
        self.assertIn("assignee_account_id", jira.create_task.call_args.kwargs)
        self.repo.update("ai-test", lambda m: {**m, "actionItems": [{**t, "status": "done"} if t["id"] == task_id else t for t in m["actionItems"]]})
        again = self.service.process("ai-test")
        self.assertEqual(len(again["actionItems"]), 2)
        self.assertEqual(again["actionItems"][-1]["jiraIssueKey"], "KAN-51")
        self.assertEqual(again["actionItems"][-1]["status"], "done")
        self.service.create_jira_issue("ai-test", task_id, jira)
        self.assertEqual(jira.create_task.call_count, 1)

    def test_incomplete_follow_up_requires_review_then_reprocessing_keeps_resolution(self):
        proposal = self.service.process("ai-test")["followUps"][0]
        with self.assertRaises(MeetingError): self.service.approve_follow_up("ai-test", proposal["id"], {})
        self.assertEqual(len(self.service.list()), 1)
        result = self.service.approve_follow_up("ai-test", proposal["id"], {"date": "2026-10-09", "startTime": "14:00", "endTime": "14:30", "participants": [MAYA]})
        self.assertEqual(result["meeting"]["status"], "scheduled")
        again = self.service.process("ai-test")
        self.assertEqual(len(again["followUps"]), 1)
        self.assertEqual(again["followUps"][0]["status"], "approved")
        self.assertEqual(again["followUps"][0]["scheduledMeetingId"], result["meeting"]["id"])
        self.assertEqual(len(self.service.list()), 2)

    def test_dismissed_ai_follow_up_stays_dismissed_after_reprocessing(self):
        proposal = self.service.process("ai-test")["followUps"][0]
        self.service.dismiss_follow_up("ai-test", proposal["id"])
        self.assertEqual(self.service.process("ai-test")["followUps"][0]["status"], "dismissed")

    def test_jira_update_during_processing_is_preserved(self):
        def analyze(_):
            self.repo.update("ai-test", lambda m: {**m, "actionItems": [{**t, "jiraIssueKey": "KAN-52"} for t in m["actionItems"]]})
            return intelligence()
        self.provider.analyze.side_effect = analyze
        self.assertEqual(self.service.process("ai-test")["actionItems"][0]["jiraIssueKey"], "KAN-52")

    def test_changed_transcript_during_processing_discards_stale_result(self):
        def analyze(_):
            self.repo.update("ai-test", lambda m: {**m, "transcript": [*m["transcript"], {"timestamp": "", "speaker": ALEX, "text": "New correction"}]})
            return intelligence()
        self.provider.analyze.side_effect = analyze
        with self.assertRaises(AIProcessingFailed): self.service.process("ai-test")
        saved = self.service.get("ai-test")
        self.assertEqual(saved["transcript"][-1]["text"], "New correction")
        self.assertEqual(saved["summary"], source()["summary"])
        self.assertEqual(saved["aiStatus"], "failed")

    def test_missing_provider_configuration_is_a_failed_processing_attempt(self):
        service = MeetingService(self.repo)
        with patch.dict("os.environ", {"AI_PROVIDER": "gemini", "AI_MODEL": "", "GEMINI_API_KEY": ""}):
            with self.assertRaises(AIProcessingFailed): service.process("ai-test")
        self.assertEqual(service.get("ai-test")["aiStatus"], "failed")


class GeminiAdapterTests(unittest.TestCase):
    def setUp(self):
        self.provider = GeminiProvider("unit-test-model", "unit-test-key")
        self.response = Mock(status_code=200)
        self.response.json.return_value = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(intelligence())}]}}]}

    def test_structured_request_uses_configured_model_and_private_header(self):
        with patch("gemini_provider.requests.post", return_value=self.response) as post:
            result = self.provider.analyze({"transcript": []})
        self.assertEqual(result, intelligence())
        args, kwargs = post.call_args
        self.assertTrue(args[0].endswith("/unit-test-model:generateContent"))
        self.assertNotIn("unit-test-key", args[0])
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "unit-test-key")
        self.assertEqual(kwargs["json"]["generationConfig"]["responseJsonSchema"], INTELLIGENCE_SCHEMA)
        self.assertEqual(kwargs["timeout"], (10, 60))
        self.assertFalse(kwargs["allow_redirects"])

    def test_http_quota_auth_and_timeout_errors_have_no_fallback(self):
        for status in (301, 400, 401, 403, 429, 500, 503):
            with self.subTest(status=status), patch("gemini_provider.requests.post", return_value=Mock(status_code=status)):
                with self.assertRaises(AIProviderError): self.provider.analyze({})
        with patch("gemini_provider.requests.post", side_effect=requests.Timeout("private detail")):
            with self.assertRaises(AIProviderError): self.provider.analyze({})

    def test_blocked_truncated_missing_and_malformed_responses_fail(self):
        for body in ({}, {"candidates": []}, {"candidates": [{"finishReason": "MAX_TOKENS"}]}, {"candidates": [{"finishReason": "SAFETY"}]}, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}]}):
            self.response.json.return_value = body
            with patch("gemini_provider.requests.post", return_value=self.response):
                with self.assertRaises(AIProviderError): self.provider.analyze({})

    def test_provider_selection_and_model_are_environment_driven(self):
        with patch.dict("os.environ", {"AI_PROVIDER": "gemini", "AI_MODEL": "models/configured-model", "GEMINI_API_KEY": "test-only"}):
            self.assertEqual(create_ai_provider().model, "configured-model")
        for config in ({"AI_PROVIDER": "grok"}, {"AI_PROVIDER": "gemini", "AI_MODEL": ""}, {"AI_PROVIDER": "gemini", "AI_MODEL": "../invalid", "GEMINI_API_KEY": "test-only"}):
            with patch.dict("os.environ", config):
                with self.assertRaises(AIProviderError): create_ai_provider()


class ProcessingRouteTests(unittest.TestCase):
    def test_json_success_failure_and_not_found(self):
        provider = Mock()
        provider.analyze.return_value = intelligence()
        service = MeetingService(InMemoryMeetingRepository([source()]), provider)
        route = function_app.process_meeting._function.get_user_function()
        def post(meeting_id):
            return route(func.HttpRequest(method="POST", url=f"http://localhost/api/meetings/{meeting_id}/process", body=b"", route_params={"meeting_id": meeting_id}))
        with patch.object(function_app, "meetings", service):
            response = post("ai-test")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "application/json")
            self.assertEqual(json.loads(response.get_body())["aiStatus"], "processed")
            provider.analyze.side_effect = RuntimeError("secret key")
            response = post("ai-test")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(json.loads(response.get_body())["error"]["code"], "ai_processing_failed")
            self.assertNotIn(b"secret", response.get_body())
            self.assertEqual(post("missing").status_code, 404)
