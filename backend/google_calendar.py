"""Backend-only OAuth and Google Calendar REST boundary. No meeting writes here."""

from datetime import datetime, timezone
import hashlib
import os
import secrets
import time
from urllib.parse import urlencode, urlparse
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from meeting_errors import MeetingError

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events.owned"
# Stable organizer identity prevents retries from creating on a different account.
# No email/profile, calendar-list, or full-calendar permissions are requested.
SCOPES = {CALENDAR_SCOPE, "openid"}
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
COOKIE_NAME = "synq_google_oauth"


class CalendarError(MeetingError):
    status_code = 502
    code = "google_calendar_error"


class CalendarConfigError(CalendarError):
    status_code = 503


def settings():
    names = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI",
             "GOOGLE_TOKEN_ENCRYPTION_KEY", "GOOGLE_CALENDAR_TIME_ZONE")
    values = {name: os.environ.get(name, "").strip() for name in names}
    if not all(values.values()):
        raise CalendarConfigError("Google Calendar is not configured on the backend.")
    uri = urlparse(values["GOOGLE_REDIRECT_URI"])
    if (uri.scheme != "https" and not (uri.scheme == "http" and uri.hostname in ("localhost", "127.0.0.1"))) or uri.username or uri.query or uri.fragment or not uri.hostname:
        raise CalendarConfigError("Google Calendar redirect configuration is invalid.")
    try:
        ZoneInfo(values["GOOGLE_CALENDAR_TIME_ZONE"])
    except (ZoneInfoNotFoundError, ValueError):
        raise CalendarConfigError("Google Calendar timezone configuration is invalid.") from None
    return values


class GoogleCalendar:
    def __init__(self, store, config, http=requests):
        self.store, self.config, self.http = store, config, http

    def _request(self, method, url, **kwargs):
        try:
            return self.http.request(method, url, timeout=(10, 30), allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise CalendarError("Google Calendar is unavailable. The Synq meeting is saved; retry Calendar creation.") from None

    @staticmethod
    def _json(response):
        if not 200 <= response.status_code < 300:
            raise CalendarError("Google Calendar rejected the request. Check consent and retry; the Synq meeting is saved.")
        try:
            data = response.json()
        except ValueError:
            raise CalendarError("Google Calendar returned an invalid response. Retry Calendar creation.") from None
        if not isinstance(data, dict):
            raise CalendarError("Google Calendar returned an invalid response.")
        return data

    def status(self):
        connection = self.store.get("connection")
        return {"configured": True, "connected": bool(connection and connection.get("refresh_token") and not connection.get("revoked")),
                "timeZone": self.config["GOOGLE_CALENDAR_TIME_ZONE"]}

    def start_authorization(self):
        state, binding = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        # One pending authorization per shared workspace, bounded storage.
        self.store.put("oauth_state", {"state": state, "binding": binding, "expires": time.time() + 600})
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": self.config["GOOGLE_CLIENT_ID"], "redirect_uri": self.config["GOOGLE_REDIRECT_URI"],
            "response_type": "code", "scope": " ".join(sorted(SCOPES)), "state": state,
            "access_type": "offline", "prompt": "consent",
        })
        return url, binding

    def finish_authorization(self, state, binding, code, error=None):
        pending = self.store.get("oauth_state")
        if not pending or pending["expires"] < time.time() or not state or not binding or not secrets.compare_digest(pending["state"], state) or not secrets.compare_digest(pending["binding"], binding):
            raise CalendarError("Google authorization expired or did not originate in this browser. Connect again.")
        consumed = self.store.consume("oauth_state")
        if consumed != pending:
            raise CalendarError("Google authorization has already been used. Connect again.")
        if error or not code:
            raise CalendarError("Google Calendar authorization was not granted. You can connect again.")
        token = self._json(self._request("POST", "https://oauth2.googleapis.com/token", data={
            "client_id": self.config["GOOGLE_CLIENT_ID"], "client_secret": self.config["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": self.config["GOOGLE_REDIRECT_URI"], "code": code, "grant_type": "authorization_code",
        }))
        if not SCOPES.issubset(set(token.get("scope", "").split())) or not token.get("access_token") or not token.get("refresh_token"):
            raise CalendarError("Google Calendar offline permission was not granted. Connect again and allow the requested access.")
        identity = self._json(self._request("GET", "https://openidconnect.googleapis.com/v1/userinfo",
                                          headers={"Authorization": "Bearer " + token["access_token"]}))
        if not isinstance(identity.get("sub"), str) or not identity["sub"]:
            raise CalendarError("Unable to verify the connected Google account.")
        # Store only the necessary token fields, encrypted at rest.
        self.store.put("connection", {"accountId": hashlib.sha256(identity["sub"].encode()).hexdigest(),
                                      "refresh_token": token["refresh_token"]})

    def connection(self):
        connection = self.store.get("connection")
        if not connection or not connection.get("refresh_token") or connection.get("revoked"):
            return None
        return connection

    def _access_token(self, connection):
        response = self._request("POST", "https://oauth2.googleapis.com/token", data={
            "client_id": self.config["GOOGLE_CLIENT_ID"], "client_secret": self.config["GOOGLE_CLIENT_SECRET"],
            "refresh_token": connection["refresh_token"], "grant_type": "refresh_token",
        })
        if response.status_code in (400, 401):
            # Do not overwrite a different connection completed concurrently.
            latest = self.store.get("connection")
            if latest == connection:
                self.store.put("connection", {**connection, "revoked": True})
            raise CalendarError("Google Calendar authorization expired. Reconnect the original Google account, then retry.")
        token = self._json(response)
        if not isinstance(token.get("access_token"), str) or not token["access_token"]:
            raise CalendarError("Unable to obtain Google Calendar access. Reconnect and retry.")
        return token["access_token"]

    @staticmethod
    def _event_metadata(event, request_id, meeting_id):
        link = event.get("htmlLink", "")
        parsed = urlparse(link) if isinstance(link, str) else None
        if event.get("id") != request_id or event.get("status") == "cancelled" or event.get("extendedProperties", {}).get("private", {}).get("synqMeetingId") != meeting_id or not parsed or parsed.scheme != "https" or parsed.hostname not in ("calendar.google.com", "www.google.com") or parsed.username:
            raise CalendarError("Google Calendar did not confirm a usable Synq event. No event link was saved; retry or check Google Calendar.")
        return {"eventId": event["id"], "eventUrl": link}

    def ensure_event(self, meeting, source, connection, zone):
        # Google supports caller-supplied event IDs. This is an idempotency key,
        # not fabricated success metadata: IDs/URLs are saved only after Google confirms.
        request_id = uuid5(NAMESPACE_URL, "synq:google-calendar:" + meeting["id"]).hex
        headers = {"Authorization": "Bearer " + self._access_token(connection)}
        existing = self._request("GET", EVENTS_URL + "/" + request_id, headers=headers)
        if existing.status_code != 404:
            return self._event_metadata(self._json(existing), request_id, meeting["id"])
        attendees = []
        seen = set()
        for person in meeting["participants"]:
            email = person.get("email", "").strip()
            if not email:
                raise CalendarError("Add an email for every participant using Edit Meeting, then retry Google Calendar. No invitations were sent.")
            if email.casefold() not in seen:
                attendees.append({"email": email, "displayName": person["name"]})
                seen.add(email.casefold())
        def date_time(field):
            naive = datetime.fromisoformat(meeting["date"] + "T" + meeting[field])
            tz = ZoneInfo(zone)
            aware = naive.replace(tzinfo=tz)
            if aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != naive or aware.utcoffset() != naive.replace(tzinfo=tz, fold=1).utcoffset():
                raise CalendarError("This time is ambiguous or unavailable due to daylight saving time. Edit the meeting time, then retry.")
            return {"dateTime": aware.isoformat(), "timeZone": zone}
        body = {"id": request_id, "summary": meeting["title"], "start": date_time("startTime"),
                "end": date_time("endTime"), "attendees": attendees,
                "description": f"Follow-up to Synq meeting: {source['title']} (ID: {source['id']}).\n\n{meeting['agenda']}",
                "extendedProperties": {"private": {"synqMeetingId": meeting["id"], "synqSourceMeetingId": source["id"]}}}
        response = self._request("POST", EVENTS_URL, headers=headers, params={"sendUpdates": "all"}, json=body)
        if response.status_code == 409:
            response = self._request("GET", EVENTS_URL + "/" + request_id, headers=headers)
        return self._event_metadata(self._json(response), request_id, meeting["id"])
