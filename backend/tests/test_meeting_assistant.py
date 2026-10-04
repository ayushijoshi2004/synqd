"""Offline boundary tests using the real SDK with mocked Gemini transport."""
from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

import support  # noqa: F401
import azure.functions as func
import httpx
import function_app
from meeting_assistant import MAX_CONTEXT_BYTES, SYSTEM_INSTRUCTION, meeting_context
from meeting_repository import InMemoryMeetingRepository
from meeting_service import MeetingService

ALEX = {"id": "alex", "name": "Alex Rivera", "color": "#333"}


def source():
    return {
        "id": "ask-test", "title": "Checkout review", "date": "2026-10-01",
        "startTime": "10:00", "endTime": "11:00", "participants": [ALEX],
        "project": "Atlas", "team": "Payments", "agenda": "Checkout", "status": "ended",
        "aiStatus": "processed", "preview": "",
        "transcript": [{"speaker": ALEX, "timestamp": "00:10", "text":
                        "I will fix the declined-card retry bug by Friday. We decided to finish checkout error states before launch."}],
        "summary": {"beforeHighlight": "Checkout review", "highlight": "", "afterHighlight": "", "points": []},
        "decisions": [{"id": "d1", "text": "Finish checkout error states before launch", "participant": ALEX, "timestamp": "00:10", "note": ""}],
        "actionItems": [{"id": "t1", "text": "Fix declined-card retry bug", "due": "Friday", "assignee": ALEX, "status": "todo"}],
        "unresolvedItems": ["Launch date is undecided"], "followUps": [],
    }


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryMeetingRepository([source(), {**source(), "id": "other", "title": "PRIVATE OTHER MEETING"}])
        self.service = MeetingService(self.repo)
        p = patch.object(function_app, "meetings", self.service)
        p.start(); self.addCleanup(p.stop)
        env = {key: value for key, value in os.environ.items() if "proxy" not in key.lower()}
        env.update({"GEMINI_API_KEY": "test-secret", "AI_MODEL": "gemini-2.5-flash"})
        p = patch.dict(os.environ, env, clear=True)
        p.start(); self.addCleanup(p.stop)
        p = patch("httpx.Client.send", side_effect=AssertionError("Unexpected network call"))
        self.send = p.start(); self.addCleanup(p.stop)

    def request(self, payload, meeting_id="ask-test", raw=False):
        req = func.HttpRequest(method="POST", url="http://localhost/api/meetings/ask-test/ask",
                               route_params={"meeting_id": meeting_id},
                               body=payload if raw else json.dumps(payload).encode())
        result = function_app.ask_meeting(req)
        return result.status_code, json.loads(result.get_body())

    def sdk_reply(self, answer):
        def send(request, **kwargs):
            self.sent = json.loads(request.content)
            return httpx.Response(200, request=request, json={"candidates": [{
                "content": {"role": "model", "parts": [{"text": answer}]}, "finishReason": "STOP",
            }]})
        self.send.side_effect = send

    def test_decisions_and_owners_and_unknown_answer_contract(self):
        # These are controlled provider answers, NOT a live grounding evaluation.
        for question, answer in [
            ("What were the main decisions?", "Finish checkout error states before launch."),
            ("What is Alex responsible for?", "Alex Rivera will fix the declined-card retry bug by Friday."),
            ("What is the marketing budget?", "This meeting does not contain enough information to answer that question."),
        ]:
            with self.subTest(question=question):
                self.sdk_reply(answer)
                status, body = self.request({"question": question})
                self.assertEqual((status, body), (200, {"answer": answer}))
                context = json.loads(self.sent["contents"][0]["parts"][0]["text"])
                self.assertEqual(context["question"], question)
                self.assertEqual(context["meeting"]["actionItems"][0]["assignee"]["name"], "Alex Rivera")
                self.assertEqual(context["meeting"]["transcript"][0]["speaker"]["name"], "Alex Rivera")
                self.assertEqual(context["meeting"]["decisions"][0]["text"], source()["decisions"][0]["text"])
                self.assertNotIn("PRIVATE OTHER MEETING", json.dumps(context))
                self.assertIn("ONLY", self.sent["systemInstruction"]["parts"][0]["text"])
        self.assertEqual(self.repo.get("ask-test"), source())

    def test_validation_and_not_found(self):
        for payload in ({}, {"question": "  "}, {"question": 42}, [], {"question": "x" * 2001},
                        {"question": "q", "history": "bad"}, {"question": "q", "history": [{}]}):
            self.assertEqual(self.request(payload)[0], 400)
        self.assertEqual(self.request(b"{", raw=True)[0], 400)
        for meeting_id in ("missing", "../other", "__synq_google_tokens", "__synq_vexa_claim"):
            status, body = self.request({"question": "q"}, meeting_id)
            self.assertEqual((status, body["error"]["code"]), (404, "meeting_not_found"))
        self.send.assert_not_called()

    def test_clean_errors_timeout_missing_key_and_bad_output(self):
        for failure in (RuntimeError("test-secret raw error"), httpx.ReadTimeout("secret timeout")):
            self.send.side_effect = failure
            status, body = self.request({"question": "q"})
            self.assertEqual(status, 503)
            self.assertNotIn("secret", json.dumps(body))
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            self.assertEqual(self.request({"question": "q"})[0], 503)
        for answer in ("", "x" * 12001):
            self.sdk_reply(answer)
            self.assertEqual(self.request({"question": "q"})[0], 503)
        self.send.side_effect = lambda request, **kw: httpx.Response(429, request=request, json={"error": {"message": "secret"}})
        self.assertEqual(self.request({"question": "q"})[0], 503)
        self.send.side_effect = lambda request, **kw: httpx.Response(200, request=request, json={"candidates": [{"finishReason": "MAX_TOKENS"}]})
        self.assertEqual(self.request({"question": "q"})[0], 503)

    def test_empty_intelligence_and_follow_up_history(self):
        empty = {key: value for key, value in source().items() if key not in (
            "transcript", "summary", "decisions", "actionItems", "unresolvedItems", "followUps")}
        self.repo.update("ask-test", lambda _: empty)
        answer = "This meeting does not contain enough information to answer that question."
        self.sdk_reply(answer)
        history = [{"question": "What is Alex doing?", "answer": "He owns the retry bug."}]
        self.assertEqual(self.request({"question": "When is it due?", "history": history})[1], {"answer": answer})
        sent = json.loads(self.sent["contents"][0]["parts"][0]["text"])
        self.assertEqual(sent["history"], history)
        self.assertEqual(sent["meeting"]["transcript"], [])
        self.assertIn("NOT factual evidence", SYSTEM_INSTRUCTION)

    def test_allowlist_and_size_cap(self):
        record = deepcopy(source())
        record.update({"_etag": "SECRET", "googleCalendar": {"token": "SECRET"},
                       "transcription": {"token": "SECRET"}, "projectOverview": {"description": "SECRET"}})
        record["participants"][0]["email"] = "SECRET"
        record["actionItems"][0]["jiraIssueUrl"] = "SECRET"
        self.assertNotIn("SECRET", json.dumps(meeting_context(record)))
        record["transcript"][0]["text"] = "😀" * MAX_CONTEXT_BYTES
        self.repo.update("ask-test", lambda _: record)
        status, body = self.request({"question": "q"})
        self.assertEqual((status, body["error"]["code"]), (413, "assistant_context_too_large"))
        self.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
