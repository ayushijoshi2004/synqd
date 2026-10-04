"""Offline Vexa contract and Azure HTTP handler tests."""
import json
import os
import unittest
from unittest.mock import Mock, patch

import support  # noqa: F401
import azure.functions as func
import requests
import function_app
from vexa_service import get_transcript, get_session, stop_session, join_meeting, parse_meeting_id, VexaError
from api_http import respond

MEET_ID = "abc-defg-hij"
SEGMENT = {"segment_id": "ch-0:1", "speaker": "Ria Joshi", "text": "Approve the changes.",
           "absolute_start_time": "2026-10-03T22:00:31.227000Z",
           "absolute_end_time": "2026-10-03T22:00:48.259000Z", "completed": True}


class VexaTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"VEXA_BOT_KEY": "test-bot", "VEXA_TRANSCRIPT_KEY": "test-transcript",
                                      "VEXA_API_BASE": "https://api.cloud.vexa.ai"})
        env.start()
        self.addCleanup(env.stop)
        http = patch("vexa_service.requests.request")
        self.http = http.start()
        self.addCleanup(http.stop)
        self.http.return_value = Mock(status_code=200)

    def request(self, method, body=None):
        return func.HttpRequest(method=method, url="http://localhost/api/meetings/join", headers={},
                                params={}, route_params={"meeting_id": MEET_ID},
                                body=json.dumps(body).encode() if body is not None else b"")

    def test_url_and_raw_id(self):
        for value in [MEET_ID, f"https://meet.google.com/{MEET_ID}", f"https://meet.google.com/{MEET_ID}?authuser=1"]:
            self.assertEqual(parse_meeting_id(value), MEET_ID)

    def test_invalid_urls(self):
        for value in [None, [], "", "http://meet.google.com/abc-defg-hij", "https://evil.test/abc-defg-hij",
                      "https://meet.google.com.evil.test/abc-defg-hij", "https://user@meet.google.com/abc-defg-hij",
                      "https://meet.google.com/abc-defg-hij/extra", "https://["]:
            with self.subTest(value=value), self.assertRaises(VexaError):
                parse_meeting_id(value)
        self.http.assert_not_called()

    def test_join_endpoint_and_bot_key(self):
        self.http.return_value.json.return_value = {"id": 31549, "secret": "upstream", "status": "active"}
        response = respond(lambda: join_meeting({"meetingUrl": f"https://meet.google.com/{MEET_ID}"}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.get_body()), {"id": 31549, "meetingId": MEET_ID, "status": "requested"})
        args, kwargs = self.http.call_args
        self.assertEqual(args, ("POST", "https://api.cloud.vexa.ai/bots"))
        self.assertEqual(kwargs["headers"]["X-API-Key"], "test-bot")
        self.assertEqual(kwargs["json"], {"platform": "google_meet", "native_meeting_id": MEET_ID, "bot_name": "Synq AI"})
        self.assertFalse(kwargs["allow_redirects"])

    def test_transcript_endpoint_strict_completed_and_transcript_key(self):
        self.http.return_value.json.return_value = {"segments": [SEGMENT, {**SEGMENT, "completed": False},
            {**SEGMENT, "completed": "true"}, {**SEGMENT, "completed": 1}, {"text": "pending"}]}
        response = respond(lambda: get_transcript(MEET_ID))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.get_body()), [{"id": "ch-0:1", "speaker": "Ria Joshi",
            "text": SEGMENT["text"], "startTime": SEGMENT["absolute_start_time"],
            "endTime": SEGMENT["absolute_end_time"], "completed": True}])
        args, kwargs = self.http.call_args
        self.assertEqual(args, ("GET", f"https://api.cloud.vexa.ai/transcripts/google_meet/{MEET_ID}"))
        self.assertEqual(kwargs["headers"]["X-API-Key"], "test-transcript")

    def test_empty_transcript(self):
        self.http.return_value.json.return_value = {"segments": []}
        self.assertEqual(get_transcript(MEET_ID), [])

    def test_no_deduplication(self):
        self.http.return_value.json.return_value = {"segments": [SEGMENT, SEGMENT]}
        self.assertEqual(len(get_transcript(MEET_ID)), 2)

    def test_missing_keys_are_independent(self):
        for key, operation in [("VEXA_BOT_KEY", lambda: join_meeting({"meetingUrl": MEET_ID})),
                               ("VEXA_TRANSCRIPT_KEY", lambda: get_transcript(MEET_ID))]:
            with patch.dict(os.environ, {key: ""}), self.assertRaises(VexaError) as error:
                operation()
            self.assertEqual(error.exception.status_code, 503)
        self.http.assert_not_called()

    def test_upstream_errors_are_safe(self):
        for status, code, output_status in [(401, "vexa_authentication_error", 502), (403, "vexa_permission_error", 502),
                (404, "transcript_not_found", 404), (400, "vexa_upstream_error", 502),
                (429, "vexa_upstream_error", 502), (500, "vexa_upstream_error", 502), (302, "vexa_upstream_error", 502)]:
            self.http.return_value.status_code = status
            self.http.return_value.text = "private upstream credentials"
            response = respond(lambda: get_transcript(MEET_ID))
            self.assertEqual(response.status_code, output_status)
            self.assertEqual(json.loads(response.get_body())["error"]["code"], code)
            self.assertNotIn(b"private", response.get_body())

    def test_transport_errors_are_safe(self):
        for exception, status in [(requests.Timeout("test-transcript"), 504), (requests.ConnectionError("test-transcript"), 502)]:
            self.http.side_effect = exception
            response = respond(lambda: get_transcript(MEET_ID))
            self.assertEqual(response.status_code, status)
            self.assertNotIn(b"test-transcript", response.get_body())

    def test_malformed_transcript(self):
        for data in [[], {}, {"segments": {}}, {"segments": [None]}, {"segments": [{"completed": True}]},
                     {"segments": [{**SEGMENT, "speaker": None}]}]:
            self.http.return_value.json.return_value = data
            with self.assertRaises(VexaError) as error:
                get_transcript(MEET_ID)
            self.assertEqual(error.exception.code, "vexa_invalid_response")

    def test_non_json(self):
        self.http.return_value.json.side_effect = ValueError("private upstream payload")
        response = respond(lambda: get_transcript(MEET_ID))
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(b"private", response.get_body())

    def test_malformed_join(self):
        for data in [{}, {"id": True}, {"id": "secret"}, {"id": -1}]:
            self.http.return_value.json.return_value = data
            with self.assertRaises(VexaError):
                join_meeting({"meetingUrl": MEET_ID})

    def test_invalid_body(self):
        for body in [[], {}, {"meetingUrl": 123}]:
            self.assertEqual(function_app.join_meeting(self.request("POST", body)).status_code, 400)
        self.assertEqual(function_app.join_meeting(self.request("POST")).status_code, 400)
        self.http.assert_not_called()

    def test_configuration_error(self):
        with patch.dict(os.environ, {"VEXA_API_BASE": "http://unsafe.test"}):
            response = respond(lambda: get_transcript(MEET_ID))
        self.assertEqual(response.status_code, 503)
        self.http.assert_not_called()


    def test_record_specific_transcripts_verify_identity_and_support_relative_times(self):
        data = {"id": 101, "platform": "google_meet", "native_meeting_id": MEET_ID, "status": "active",
                "segments": [{**SEGMENT, "start": 12.5}, {**SEGMENT, "completed": False}]}
        self.http.return_value.json.return_value = data
        result = get_session(101, MEET_ID)
        self.assertEqual(result["segments"][0]["timestamp"], "00:12")
        self.assertEqual(len(result["segments"]), 1)
        self.assertEqual(self.http.call_args.args[1], "https://api.cloud.vexa.ai/transcripts/by-id/101")
        for field, value in (("id", 102), ("native_meeting_id", "xxx-yyyy-zzz"), ("platform", "zoom")):
            self.http.return_value.json.return_value = {**data, field: value}
            with self.assertRaises(VexaError): get_session(101, MEET_ID)

    def test_stop_verifies_latest_record_before_native_key_delete(self):
        self.http.return_value.json.return_value = {"id": 999, "platform": "google_meet", "native_meeting_id": MEET_ID}
        with self.assertRaises(VexaError): stop_session(101, MEET_ID)
        self.assertEqual(self.http.call_count, 1)
        self.http.reset_mock()
        self.http.side_effect = [Mock(status_code=200, json=lambda: {"id": 101, "platform": "google_meet", "native_meeting_id": MEET_ID, "status": "active"}),
                                 Mock(status_code=200, json=lambda: {"meeting_id": 101, "status": "stopping"})]
        stop_session(101, MEET_ID)
        self.assertEqual(self.http.call_args.args, ("DELETE", f"https://api.cloud.vexa.ai/bots/google_meet/{MEET_ID}"))
        self.assertEqual(self.http.call_args.kwargs["headers"]["X-API-Key"], "test-bot")
