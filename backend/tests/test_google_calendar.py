"""Google is mocked throughout. No secrets, cloud writes, or invitations in tests."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse
from uuid import NAMESPACE_URL, uuid5

import requests
from azure.cosmos import exceptions
from cryptography.fernet import Fernet
import azure.functions as func
import support
import function_app
from google_calendar import GoogleCalendar, CalendarError, CalendarConfigError, CALENDAR_SCOPE, settings
from google_calendar_store import GoogleCalendarStore, PRIVATE_PREFIX
from meeting_errors import FollowUpConflict, MeetingError, MeetingNotFound
from meeting_repository import InMemoryMeetingRepository
from meeting_service import MeetingService
from seed_data import load_seed_meetings


class MemoryStore:
    def __init__(self): self.records = {}
    def get(self, key): return deepcopy(self.records.get(key))
    def put(self, key, value): self.records[key] = deepcopy(value)
    def consume(self, key): return self.records.pop(key, None)


def response(status, data):
    return Mock(status_code=status, json=Mock(return_value=data))


def config():
    return {"GOOGLE_CLIENT_ID": "test-client", "GOOGLE_CLIENT_SECRET": "test-secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:7071/api/google-calendar/callback",
            "GOOGLE_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "GOOGLE_CALENDAR_TIME_ZONE": "America/New_York"}


class GoogleTests(unittest.TestCase):
    def setUp(self):
        self.store, self.http = MemoryStore(), Mock()
        self.calendar = GoogleCalendar(self.store, config(), self.http)
        self.repository = InMemoryMeetingRepository(load_seed_meetings())
        self.service = MeetingService(self.repository, calendar_factory=lambda: self.calendar)
        self.events, self.posts = {}, []
        self.failure, self.timeout_after_create = False, False
        self.store.put("connection", {"accountId": "account-a", "refresh_token": "private-refresh"})
        self.http.request.side_effect = self.google
        self.network = patch("requests.sessions.Session.request", side_effect=AssertionError("Real HTTP forbidden"))
        self.network.start(); self.addCleanup(self.network.stop)

    def google(self, method, url, **kwargs):
        if url.endswith("/token"):
            return response(200, {"access_token": "private-access"})
        if self.failure: return response(503, {"secret": "never expose this"})
        if method == "GET": return response(200, deepcopy(self.events[url.rsplit("/", 1)[-1]])) if url.rsplit("/", 1)[-1] in self.events else response(404, {})
        body = deepcopy(kwargs["json"])
        self.posts.append(kwargs)
        if body["id"] in self.events: return response(409, {})
        self.events[body["id"]] = {**body, "htmlLink": "https://calendar.google.com/calendar/event?eid=confirmed", "status": "confirmed"}
        if self.timeout_after_create:
            self.timeout_after_create = False
            raise requests.Timeout("private transport content")
        return response(200, deepcopy(self.events[body["id"]]))

    def approve(self):
        participants = deepcopy(self.service.get("m1")["followUps"][0]["participants"])
        for i, person in enumerate(participants): person["email"] = f"reviewer{i}@example.invalid"
        return self.service.approve_follow_up("m1", "f1", {"title": "Reviewed event", "date": "2026-10-12", "startTime": "14:00", "endTime": "15:30", "participants": participants})

    def test_success_uses_reviewed_values_real_response_and_invitations(self):
        result = self.approve(); meeting = result["meeting"]
        self.assertEqual(meeting["googleCalendar"]["status"], "created")
        sent = self.posts[0]
        self.assertEqual(sent["params"], {"sendUpdates": "all"})
        self.assertEqual(sent["json"]["summary"], "Reviewed event")
        self.assertEqual(sent["json"]["start"]["dateTime"], "2026-10-12T14:00:00-04:00")
        self.assertEqual(sent["json"]["end"]["dateTime"], "2026-10-12T15:30:00-04:00")
        self.assertEqual(sent["json"]["attendees"], [{"email": p["email"], "displayName": p["name"]} for p in meeting["participants"]])
        self.assertIn("m1", sent["json"]["description"])
        self.assertEqual(self.service.get(meeting["id"]), meeting)
        self.assertEqual(result["sourceMeeting"]["followUps"][0]["scheduledMeetingId"], meeting["id"])
        self.assertNotIn("private-refresh", json.dumps(result))
        self.assertNotIn("private-access", json.dumps(result))

    def test_missing_connection_preserves_approval_and_retry_works(self):
        saved = self.store.consume("connection")
        result = self.approve(); mid = result["meeting"]["id"]
        self.assertEqual(result["meeting"]["googleCalendar"]["status"], "not_connected")
        self.http.request.assert_not_called()
        self.store.put("connection", saved)
        self.assertEqual(self.service.sync_follow_up_calendar("m1", "f1")["id"], mid)
        self.assertEqual(len(self.posts), 1)

    def test_failed_api_preserves_meeting_and_has_no_fake_metadata(self):
        self.failure = True
        result = self.approve(); state = result["meeting"]["googleCalendar"]
        self.assertEqual(state["status"], "failed")
        self.assertNotIn("eventId", state); self.assertNotIn("eventUrl", state)
        self.assertEqual(self.service.get("m1")["followUps"][0]["status"], "approved")
        self.assertNotIn("secret", state["error"])
        self.failure = False
        self.assertEqual(self.service.sync_follow_up_calendar("m1", "f1")["googleCalendar"]["status"], "created")

    def test_response_lost_after_creation_retry_does_not_send_second_invitation(self):
        self.timeout_after_create = True
        first = self.approve()["meeting"]
        self.assertEqual(first["googleCalendar"]["status"], "failed")
        # Fresh service and provider, same durable data.
        reloaded = MeetingService(self.repository, calendar_factory=lambda: GoogleCalendar(self.store, config(), self.http))
        second = reloaded.sync_follow_up_calendar("m1", "f1")
        self.assertEqual(second["googleCalendar"]["status"], "created")
        self.assertEqual(len(self.posts), 1)

    def test_duplicate_approval_still_conflicts_and_duplicate_retry_is_noop(self):
        self.approve()
        with self.assertRaises(FollowUpConflict): self.approve()
        for _ in range(3): self.service.sync_follow_up_calendar("m1", "f1")
        self.assertEqual(len(self.posts), 1)

    def test_concurrent_retries_recover_one_event_after_unknown_outcome(self):
        self.timeout_after_create = True; self.approve()
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: self.service.sync_follow_up_calendar("m1", "f1"), range(5)))
        self.assertTrue(all(item["googleCalendar"]["status"] == "created" for item in results))
        self.assertEqual(len(self.posts), 1)

    def test_configuration_failure_does_not_undo_approval(self):
        self.service.calendar_factory = Mock(side_effect=CalendarConfigError("Google Calendar is not configured on the backend."))
        result = self.approve()
        self.assertEqual(result["sourceMeeting"]["followUps"][0]["status"], "approved")
        self.assertEqual(result["meeting"]["googleCalendar"]["status"], "failed")
        self.http.request.assert_not_called()

    def test_calendar_storage_read_failure_still_returns_approved_synq_meeting(self):
        with patch.object(self.service, "sync_follow_up_calendar", side_effect=RuntimeError("storage unavailable")):
            result = self.approve()
        self.assertEqual(result["sourceMeeting"]["followUps"][0]["status"], "approved")
        self.assertEqual(result["meeting"]["googleCalendar"]["status"], "failed")
        self.assertEqual(self.service.get(result["meeting"]["id"])["status"], "scheduled")

    def test_retry_route_uses_service_and_returns_calendar_state(self):
        self.failure = True; self.approve(); self.failure = False
        req = func.HttpRequest(method="POST", url="http://localhost/api/meetings/m1/follow-ups/f1/google-calendar", body=b"",
                               route_params={"meeting_id": "m1", "follow_up_id": "f1"})
        route = function_app.retry_follow_up_calendar._function.get_user_function()
        with patch.object(function_app, "meetings", self.service):
            result = route(req)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(json.loads(result.get_body())["googleCalendar"]["status"], "created")

    def test_retry_cannot_schedule_suggested_or_dismissed_followup(self):
        with self.assertRaises(FollowUpConflict): self.service.sync_follow_up_calendar("m1", "f1")
        self.service.dismiss_follow_up("m1", "f1")
        with self.assertRaises(FollowUpConflict): self.service.sync_follow_up_calendar("m1", "f1")
        self.http.request.assert_not_called()

    def test_missing_emails_do_not_get_guessed_and_can_be_fixed(self):
        meeting = self.service.approve_follow_up("m1", "f1", {})["meeting"]
        self.assertEqual(meeting["googleCalendar"]["status"], "failed")
        self.assertIn("email", meeting["googleCalendar"]["error"])
        self.assertEqual(len(self.posts), 0)
        people = [{**p, "email": "shared@example.invalid"} for p in meeting["participants"]]
        self.service.patch(meeting["id"], {"participants": people})
        self.service.sync_follow_up_calendar("m1", "f1")
        self.assertEqual(len(self.posts[0]["json"]["attendees"]), 1)

    def test_google_metadata_is_readonly_and_email_is_optional_but_validated(self):
        with self.assertRaises(MeetingError): self.service.patch("m1", {"googleCalendar": {"status": "created", "eventId": "fake", "eventUrl": "fake"}})
        with self.assertRaises(MeetingError): self.service.patch("m1", {"participants": [{"id": "p", "name": "P", "color": "red", "email": "bad"}]})
        self.service.patch("m1", {"participants": [{"id": "p", "name": "P", "color": "red"}]})

    def test_retry_on_different_account_is_rejected_and_original_binding_survives(self):
        self.failure = True; meeting = self.approve()["meeting"]
        self.failure = False
        self.store.put("connection", {"accountId": "account-b", "refresh_token": "other"})
        result = self.service.sync_follow_up_calendar("m1", "f1")
        self.assertEqual(result["googleCalendar"]["status"], "failed")
        self.assertEqual(result["googleCalendar"]["accountId"], "account-a")
        self.assertEqual(len(self.posts), 0)
        self.store.put("connection", {"accountId": "account-a", "refresh_token": "renewed"})
        self.assertEqual(self.service.sync_follow_up_calendar("m1", "f1")["googleCalendar"]["status"], "created")

    def test_confirmed_google_metadata_save_failure_recovers_by_get(self):
        update = self.repository.update
        def failing(mid, change):
            def inspect(current):
                result = change(current)
                if result.get("googleCalendar", {}).get("status") == "created": raise RuntimeError("storage unavailable")
                return result
            return update(mid, inspect)
        with patch.object(self.repository, "update", side_effect=failing):
            result = self.approve()
        self.assertEqual(result["meeting"]["googleCalendar"]["status"], "failed")
        self.assertEqual(self.service.sync_follow_up_calendar("m1", "f1")["googleCalendar"]["status"], "created")
        self.assertEqual(len(self.posts), 1)

    def test_conflict_gets_original_google_event(self):
        self.failure = True; self.approve(); self.failure = False
        get_count = 0
        google = self.google
        def race(method, url, **kwargs):
            nonlocal get_count
            if method == "GET":
                get_count += 1
                if get_count == 1: return response(404, {})
            if method == "POST" and "json" in kwargs:
                google(method, url, **kwargs)
                return response(409, {})
            return google(method, url, **kwargs)
        self.http.request.side_effect = race
        self.assertEqual(self.service.sync_follow_up_calendar("m1", "f1")["googleCalendar"]["status"], "created")
        self.assertEqual(len(self.posts), 1)

    def test_canceled_or_unrelated_event_is_not_reported_as_success(self):
        self.timeout_after_create = True; self.approve()
        event = next(iter(self.events.values())); event["status"] = "cancelled"
        self.assertEqual(self.service.sync_follow_up_calendar("m1", "f1")["googleCalendar"]["status"], "failed")
        event["status"] = "confirmed"; event["extendedProperties"] = {}
        self.assertEqual(self.service.sync_follow_up_calendar("m1", "f1")["googleCalendar"]["status"], "failed")

    def test_dst_nonexistent_and_ambiguous_times_rejected(self):
        self.failure = True; meeting = self.approve()["meeting"]; self.failure = False
        for day, start, end in (("2026-03-08", "02:15", "03:30"), ("2026-11-01", "01:15", "02:30")):
            self.service.patch(meeting["id"], {"date": day, "startTime": start, "endTime": end})
            result = self.service.sync_follow_up_calendar("m1", "f1")
            self.assertEqual(result["googleCalendar"]["status"], "failed")
            self.assertIn("daylight", result["googleCalendar"]["error"])
        self.assertEqual(len(self.posts), 0)


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.store, self.http = MemoryStore(), Mock()
        self.calendar = GoogleCalendar(self.store, config(), self.http)

    def test_config_missing_invalid_timezone_and_redirect_are_safe(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(CalendarConfigError): settings()
        for changes in ({"GOOGLE_CALENDAR_TIME_ZONE": "not/a/zone"}, {"GOOGLE_REDIRECT_URI": "http://attacker.invalid/callback"}):
            with patch.dict(os.environ, {**config(), **changes}, clear=True), self.assertRaises(CalendarConfigError): settings()
        with patch.dict(os.environ, config(), clear=True): self.assertEqual(settings()["GOOGLE_CALENDAR_TIME_ZONE"], "America/New_York")

    def test_authorization_minimum_scopes_offline_and_single_use_browser_state(self):
        url, binding = self.calendar.start_authorization()
        params = parse_qs(urlparse(url).query)
        self.assertEqual(set(params["scope"][0].split()), {CALENDAR_SCOPE, "openid"})
        self.assertEqual(params["access_type"], ["offline"])
        self.assertNotIn("test-secret", url)
        state = params["state"][0]
        for badstate, badcookie in (("wrong", binding), (state, "wrong"), (state, "")):
            with self.assertRaises(CalendarError): self.calendar.finish_authorization(badstate, badcookie, "code")
        self.http.request.side_effect = [response(200, {"access_token": "access", "refresh_token": "refresh", "scope": CALENDAR_SCOPE + " openid"}), response(200, {"sub": "google-user"})]
        self.calendar.finish_authorization(state, binding, "code")
        self.assertTrue(self.calendar.status()["connected"])
        self.assertNotIn("refresh", json.dumps(self.calendar.status()))
        self.assertNotIn("access_token", self.store.get("connection"))
        with self.assertRaises(CalendarError): self.calendar.finish_authorization(state, binding, "code")
        self.assertEqual(self.http.request.call_count, 2)

    def test_denied_and_expired_oauth_leave_existing_connection_intact(self):
        self.store.put("connection", {"refresh_token": "old", "accountId": "a"})
        url, cookie = self.calendar.start_authorization(); state = parse_qs(urlparse(url).query)["state"][0]
        with self.assertRaises(CalendarError): self.calendar.finish_authorization(state, cookie, "", "access_denied")
        self.assertEqual(self.store.get("connection")["refresh_token"], "old")
        url, cookie = self.calendar.start_authorization(); pending = self.store.get("oauth_state"); pending["expires"] = time.time() - 1; self.store.put("oauth_state", pending)
        with self.assertRaises(CalendarError): self.calendar.finish_authorization(pending["state"], cookie, "code")
        self.http.request.assert_not_called()

    def test_missing_refresh_or_scope_and_token_failure_never_connect(self):
        for token in ({"access_token": "a", "scope": CALENDAR_SCOPE + " openid"}, {"access_token": "a", "refresh_token": "r", "scope": "openid"}):
            url, cookie = self.calendar.start_authorization(); state = parse_qs(urlparse(url).query)["state"][0]
            self.http.request.return_value = response(200, token)
            with self.assertRaises(CalendarError): self.calendar.finish_authorization(state, cookie, "code")
            self.assertFalse(self.calendar.status()["connected"])

    def test_expired_refresh_token_requires_reconnect_without_exposing_secrets(self):
        self.store.put("connection", {"accountId": "a", "refresh_token": "private"})
        self.http.request.return_value = response(400, {"error": "invalid_grant", "detail": "private"})
        with self.assertRaisesRegex(CalendarError, "Reconnect"):
            self.calendar._access_token(self.store.get("connection"))
        self.assertFalse(self.calendar.status()["connected"])

    def test_oauth_routes_cookie_and_callback_do_not_expose_tokens(self):
        def handler(name): return getattr(function_app, name)._function.get_user_function()
        req = func.HttpRequest(method="GET", url="http://localhost/api/google-calendar/authorize", body=b"")
        with patch.object(function_app, "get_google_calendar", return_value=self.calendar):
            start = handler("google_calendar_authorize")(req)
            self.assertEqual(start.status_code, 302)
            self.assertIn("HttpOnly", start.headers["Set-Cookie"])
            self.assertIn("SameSite=Lax", start.headers["Set-Cookie"])
            state = parse_qs(urlparse(start.headers["Location"]).query)["state"][0]
            self.http.request.side_effect = [response(200, {"access_token": "secret-access", "refresh_token": "secret-refresh", "scope": CALENDAR_SCOPE + " openid"}), response(200, {"sub": "subject"})]
            callback = func.HttpRequest(method="GET", url="http://localhost/api/google-calendar/callback", body=b"", params={"state": state, "code": "private-code"}, headers={"Cookie": start.headers["Set-Cookie"].split(";", 1)[0]})
            result = handler("google_calendar_callback")(callback)
            self.assertEqual(result.status_code, 200)
            self.assertNotIn(b"secret", result.get_body())
            self.assertNotIn(b"private-code", result.get_body())
            self.assertEqual(result.headers["Cache-Control"], "no-store")


class TokenStorageTests(unittest.TestCase):
    def test_encrypted_storage_reload_and_no_crud_access_to_private_records(self):
        records = {}
        def read(item, partition_key):
            if item not in records: raise exceptions.CosmosResourceNotFoundError(status_code=404)
            return deepcopy(records[item])
        def put(body): records[body["id"]] = {**deepcopy(body), "_etag": "v1"}
        container = Mock()
        container.read_item.side_effect = read; container.upsert_item.side_effect = put
        container.read_all_items.side_effect = lambda: list(records.values())
        container.delete_item.side_effect = lambda item, **kwargs: records.pop(item)
        key = Fernet.generate_key().decode()
        store = GoogleCalendarStore(container, key)
        store.put("connection", {"refresh_token": "VERY_PRIVATE"})
        self.assertNotIn("VERY_PRIVATE", json.dumps(records))
        fresh = GoogleCalendarStore(container, key)
        self.assertEqual(fresh.get("connection")["refresh_token"], "VERY_PRIVATE")
        repo = support.REAL_COSMOS_REPOSITORY.__new__(support.REAL_COSMOS_REPOSITORY); repo.container = container
        self.assertEqual(repo.list(), [])
        for action in (lambda: repo.get(PRIVATE_PREFIX + "connection"), lambda: repo.update(PRIVATE_PREFIX + "connection", lambda x: x), lambda: repo.delete(PRIVATE_PREFIX + "connection")):
            with self.assertRaises(MeetingNotFound): action()
        store.put("oauth_state", {"state": "one-time"})
        self.assertEqual(fresh.consume("oauth_state"), {"state": "one-time"})
        self.assertIsNone(fresh.consume("oauth_state"))
