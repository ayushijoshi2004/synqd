"""Offline lifecycle, concurrency, HTTP and real-Cosmos-adapter contracts."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch

import support
import azure.functions as func
import function_app
from meeting_errors import MeetingError, MeetingWriteConflict
from meeting_repository import InMemoryMeetingRepository
from meeting_service import MeetingService
from seed_data import load_seed_meetings
from transcription_service import TranscriptionService
from vexa_service import VexaError
from test_cosmos_processing import FileContainer


def source(id="m1"):
    meeting = deepcopy(load_seed_meetings()[0])
    meeting.update(id=id, googleMeetUrl="https://meet.google.com/abc-defg-hij", transcript=[], followUps=[])
    return meeting


class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryMeetingRepository([source(), source("m2")])
        self.provider = Mock()
        self.provider.join_meeting.return_value = {"id": 101}
        self.provider.get_session.return_value = {"status": "active", "segments": []}
        self.now = 1000
        self.service = MeetingService(self.repo)
        self.flow = TranscriptionService(self.repo, self.provider, lambda: self.now)
        self.service.transcription = self.flow

    def start(self, id="m1"):
        return self.service.join_meeting({"synqMeetingId": id})

    def tick(self, seconds=11):
        self.now += seconds
        self.service.poll_transcriptions()

    def segment(self, id="s1", text="Saved to the correct meeting"):
        return {"id": id, "speaker": "Unknown guest", "text": text, "timestamp": "00:12"}

    def test_start_and_repeat_use_saved_link_and_one_bot(self):
        first = self.start()
        second = self.start()
        self.assertEqual(first["transcription"], second["transcription"])
        self.provider.join_meeting.assert_called_once_with({"meetingUrl": source()["googleMeetUrl"]})
        self.assertEqual(first["transcription"]["status"], "starting")

    def test_concurrent_double_join_and_cross_meeting_link_claim(self):
        entered, release = threading.Event(), threading.Event()
        def create(_):
            entered.set(); self.assertTrue(release.wait(3)); return {"id": 101}
        self.provider.join_meeting.side_effect = create
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.start)
            self.assertTrue(entered.wait(3))
            self.assertEqual(self.start()["transcription"]["status"], "starting")
            with self.assertRaises(VexaError): self.start("m2")
            release.set(); first.result()
        self.provider.join_meeting.assert_called_once()

    def test_missing_link_unknown_and_invalid_id(self):
        self.repo.update("m1", lambda m: {**m, "googleMeetUrl": ""})
        with self.assertRaisesRegex(MeetingError, "no Google Meet link"): self.start()
        for value in ({}, {"synqMeetingId": []}, {"synqMeetingId": "../private"}, {"meetingUrl": source()["googleMeetUrl"]}):
            with self.assertRaises(MeetingError): self.service.join_meeting(value)
        with self.assertRaises(MeetingError) as error: self.start("missing")
        self.assertEqual(error.exception.status_code, 404)
        self.provider.join_meeting.assert_not_called()

    def test_completed_segments_are_deduplicated_and_bound_to_record(self):
        self.start()
        self.provider.get_session.return_value = {"status": "active", "segments": [self.segment(), self.segment()]}
        self.tick(); self.tick()
        self.assertEqual(len(self.repo.get("m1")["transcript"]), 1)
        self.assertEqual(self.repo.get("m2")["transcript"], [])
        self.provider.get_session.assert_called_with(101, "abc-defg-hij")
        # A new service (browser/backend handler reload) reads the same cursor.
        fresh = TranscriptionService(self.repo, self.provider, lambda: self.now + 20)
        fresh.poll_pending()
        self.assertEqual(len(self.repo.get("m1")["transcript"]), 1)

    def test_end_drains_late_final_segments_and_repeated_end_is_idempotent(self):
        self.start()
        result = self.service.end_transcription("m1")
        self.assertEqual(result["transcription"]["status"], "stopping")
        self.service.end_transcription("m1")
        self.provider.stop_session.assert_called_once_with(101, "abc-defg-hij")
        self.provider.get_session.return_value = {"status": "completed", "segments": [self.segment()]}
        self.tick()
        self.provider.get_session.return_value["segments"].append(self.segment("s2", "Last sentence"))
        self.tick(20); self.tick(31)
        saved = self.repo.get("m1")
        self.assertEqual(saved["transcription"]["status"], "completed")
        self.assertFalse(saved["transcription"]["polling"])
        self.assertEqual(len(saved["transcript"]), 2)
        calls = self.provider.get_session.call_count
        self.tick(); self.service.end_transcription("m1"); self.start()
        self.assertEqual(self.provider.get_session.call_count, calls)
        self.provider.join_meeting.assert_called_once()

    def test_reused_meet_link_has_new_record_and_never_old_transcript(self):
        self.start()
        self.provider.get_session.return_value = {"status": "completed", "segments": [self.segment()]}
        self.tick(); self.tick(31)
        self.provider.join_meeting.return_value = {"id": 202}
        self.start("m2")
        self.provider.get_session.return_value = {"status": "active", "segments": [self.segment("s1", "New session text")]}
        self.tick()
        self.assertEqual(self.repo.get("m2")["transcript"][0]["text"], "New session text")
        self.assertEqual(self.repo.get("m1")["transcript"][0]["text"], self.segment()["text"])
        self.provider.get_session.assert_called_with(202, "abc-defg-hij")

    def test_provider_reusing_old_record_fails_closed(self):
        self.start()
        self.provider.get_session.return_value = {"status": "completed", "segments": []}
        self.tick(); self.tick(31)
        with self.assertRaisesRegex(VexaError, "another session"): self.start("m2")
        self.assertNotIn("botId", self.repo.get("m2")["transcription"])

    def test_uncertain_spawn_is_never_replayed(self):
        self.provider.join_meeting.side_effect = VexaError("Vexa request timed out.")
        with self.assertRaises(VexaError): self.start()
        with self.assertRaises(VexaError): self.start()
        self.assertEqual(self.repo.get("m1")["transcription"]["status"], "error")
        self.provider.join_meeting.assert_called_once()

    def test_poll_failure_backoff_pause_and_safe_stop_recovery(self):
        self.start()
        self.provider.get_session.side_effect = VexaError("Vexa unavailable.")
        for _ in range(6): self.tick(301)
        state = self.repo.get("m1")["transcription"]
        self.assertEqual(state["status"], "error"); self.assertFalse(state["polling"])
        self.provider.get_session.side_effect = None
        self.service.end_transcription("m1")
        self.provider.stop_session.assert_called_once()
        self.assertTrue(self.repo.get("m1")["transcription"]["polling"])

    def test_storage_failure_does_not_advance_dedupe_cursor(self):
        self.start()
        self.provider.get_session.return_value = {"status": "active", "segments": [self.segment()]}
        original = self.repo.update
        def fail_save(id, change):
            def wrapped(m):
                value = change(m)
                if value.get("transcript"): raise RuntimeError("private Cosmos diagnostic")
                return value
            return original(id, wrapped)
        with patch.object(self.repo, "update", side_effect=fail_save): self.tick()
        saved = self.repo.get("m1")
        self.assertEqual(saved["transcript"], [])
        self.assertEqual(saved["transcription"]["segmentIds"], [])
        self.assertNotIn("private", saved["transcription"]["error"])
        self.tick(40)
        self.assertEqual(len(self.repo.get("m1")["transcript"]), 1)

    def test_stale_start_becomes_error_without_second_post(self):
        self.start()
        self.repo.update("m1", lambda m: {**m, "transcription": {**m["transcription"], "botId": None, "status": "starting"}})
        self.tick(121)
        self.assertEqual(self.repo.get("m1")["transcription"]["status"], "error")
        self.provider.join_meeting.assert_called_once()

    def test_active_mapping_and_transcript_cannot_be_patched_or_deleted(self):
        self.start()
        for value in ({"transcription": {}}, {"googleMeetUrl": ""}, {"transcript": []}):
            with self.assertRaises(MeetingError): self.service.patch("m1", value)
        with self.assertRaises(MeetingError): self.service.delete("m1")
        self.service.patch("m1", {"title": "Still editable"})

    def test_stop_failure_retains_session_and_retries_without_new_bot(self):
        self.start()
        self.provider.stop_session.side_effect = VexaError("Vexa stop failed.")
        result = self.service.end_transcription("m1")
        self.assertIn("stop failed", result["transcription"]["error"])
        self.assertFalse(result["transcription"].get("terminal", False))
        self.provider.stop_session.side_effect = None
        self.tick(40)
        self.assertTrue(self.repo.get("m1")["transcription"]["stopSent"])
        self.provider.join_meeting.assert_called_once()

    def test_http_contract_and_timer_delegate_through_meeting_service(self):
        def request(method, body=None, id="m1"):
            return func.HttpRequest(method=method, url="http://localhost/api/meetings/join", headers={}, params={},
                route_params={"meeting_id": id}, body=json.dumps(body).encode() if body is not None else b"")
        with patch.object(function_app, "meetings", self.service):
            response = function_app.join_meeting(request("POST", {"synqMeetingId": "m1"}))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(json.loads(response.get_body())["transcription"]["botId"], 101)
            self.assertEqual(function_app.get_meeting_transcript(request("GET", id="missing")).status_code, 404)
            self.assertEqual(function_app.get_meeting_transcript(request("GET")).headers["Cache-Control"], "no-store")
            self.assertEqual(function_app.end_transcription(request("POST")).status_code, 200)
            with patch.object(self.service, "poll_transcriptions") as poll:
                function_app.poll_transcriptions(Mock()); poll.assert_called_once()

    def test_cosmos_persistence_private_claims_and_fresh_service(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "cosmos.json"
            def repository():
                repo = support.REAL_COSMOS_REPOSITORY.__new__(support.REAL_COSMOS_REPOSITORY)
                repo.container = FileContainer(path)
                return repo
            self.repo = repository(); self.repo.create(source()); self.repo.create(source("m2"))
            self.flow = TranscriptionService(self.repo, self.provider, lambda: self.now)
            self.service.transcription = self.flow
            self.start()
            self.provider.get_session.return_value = {"status": "active", "segments": [self.segment()]}
            self.tick()
            fresh = TranscriptionService(repository(), self.provider, lambda: self.now + 40)
            fresh.poll_pending()
            self.assertEqual(len(repository().get("m1")["transcript"]), 1)
            self.assertEqual(len(repository().list()), 2)
            with self.assertRaises(MeetingError): repository().get("__synq_vexa_record-101")
            with self.assertRaises(VexaError): fresh.start({"synqMeetingId": "m2"})
            # Real adapter rejects a concurrent claim using its ETag.
            self.assertFalse(repository().claim_transcription("link-abc-defg-hij", "another"))

    def test_definite_spawn_refusal_can_be_retried_without_duplicate(self):
        self.provider.join_meeting.side_effect = VexaError("Key rejected", safe_to_retry=True)
        with self.assertRaises(VexaError): self.start()
        self.assertFalse(self.repo.get("m1")["transcription"]["attempted"])
        self.provider.join_meeting.side_effect = None
        self.assertEqual(self.start()["transcription"]["botId"], 101)

    def test_saved_vexa_transcript_can_use_existing_gemini_pipeline(self):
        from test_ai_processing import source as ai_source, intelligence
        original = ai_source()
        self.repo.create({**original, "googleMeetUrl": source()["googleMeetUrl"], "transcript": []})
        self.start("ai-test")
        self.provider.get_session.return_value = {"status": "completed", "segments": [
            {"id": f"segment-{i}", "speaker": line["speaker"]["name"], "text": line["text"], "timestamp": line["timestamp"]}
            for i, line in enumerate(original["transcript"])]}
        self.tick(); self.tick(31)
        self.service.ai_provider = Mock()
        self.service.ai_provider.analyze.return_value = intelligence()
        result = self.service.process("ai-test")
        self.assertEqual(result["aiStatus"], "processed")
        self.assertEqual(result["transcript"], original["transcript"])
        self.assertEqual(result["transcription"]["status"], "completed")
        self.assertEqual(result["followUps"][0]["status"], "suggested")

    def test_cosmos_etag_start_race_does_not_send_another_bot(self):
        with TemporaryDirectory() as temp:
            repo = support.REAL_COSMOS_REPOSITORY.__new__(support.REAL_COSMOS_REPOSITORY)
            repo.container = FileContainer(Path(temp) / "cosmos.json")
            repo.create(source())
            def race(body):
                repo.container.before_replace = None
                records = repo.container.records()
                records["m1"]["transcription"] = {"id": "winner", "status": "starting", "attempted": True}
                records["m1"]["_etag"] = "2"
                repo.container.save(records)
            repo.container.before_replace = race
            flow = TranscriptionService(repo, self.provider, lambda: self.now)
            result = flow.start({"synqMeetingId": "m1"})
            self.assertEqual(result["transcription"]["id"], "winner")
            self.provider.join_meeting.assert_not_called()

    def test_failed_start_commit_stops_confirmed_bot_and_retains_recovery(self):
        original = self.repo.update
        failed = False
        def update(id, change):
            def wrapped(meeting):
                nonlocal failed
                value = change(meeting)
                if value.get("transcription", {}).get("botId") and not failed:
                    failed = True
                    raise RuntimeError("Cosmos temporarily unavailable")
                return value
            return original(id, wrapped)
        with patch.object(self.repo, "update", side_effect=update):
            with self.assertRaises(VexaError): self.start()
        self.provider.stop_session.assert_called_once_with(101, "abc-defg-hij")
        saved = self.repo.get("m1")["transcription"]
        self.assertEqual(saved["botId"], 101)
        self.assertTrue(saved["stopRequested"])
        self.assertTrue(saved["polling"])
