"""Persisted transcription workflow; no threads or browser-owned Vexa state.

All external effects happen AFTER Cosmos compare-and-swap claims. Uncertain
spawn outcomes are never automatically replayed (Vexa has no idempotency key).
"""
import hashlib
import logging
import re
import time
from uuid import uuid4

from meeting_errors import MeetingError, MeetingWriteConflict
import vexa_service as vexa

ACTIVE = {"starting", "transcribing", "stopping"}
TERMINAL = {"completed", "failed"}
LEASE_SECONDS = 120
MAX_SESSION_SECONDS = 8 * 3600


def conflict(message):
    return vexa.VexaError(message, "transcription_conflict", 409)


class TranscriptionService:
    def __init__(self, repository, provider=vexa, clock=time.time):
        self.repository, self.provider, self.clock = repository, provider, clock

    def update(self, meeting_id, change):
        for attempt in range(4):
            try:
                return self.repository.update(meeting_id, change)
            except MeetingWriteConflict:
                if attempt == 3:
                    raise

    def start(self, payload):
        if (not isinstance(payload, dict) or set(payload) != {"synqMeetingId"}
                or not isinstance(payload["synqMeetingId"], str)
                or not re.fullmatch(r"[A-Za-z0-9_-]+", payload["synqMeetingId"])):
            raise MeetingError("Supply a valid synqMeetingId.")
        meeting_id = payload["synqMeetingId"]
        current = self.repository.get(meeting_id)
        prior = current.get("transcription", {})
        if prior.get("status") in ACTIVE or prior.get("status") == "completed":
            return current
        if prior.get("attempted"):
            raise conflict("A transcription session already exists. Use End transcription to recover it; another bot will not be started.")
        url = current.get("googleMeetUrl", "")
        if not url:
            raise MeetingError("This meeting has no Google Meet link. Save its link before joining.")
        native = vexa.parse_meeting_id(url)
        self.provider.check_configuration()
        session_id, now = str(uuid4()), self.clock()

        def begin(meeting):
            state = meeting.get("transcription", {})
            if state.get("status") in ACTIVE or state.get("attempted"):
                raise conflict("Transcription is already starting. Refresh to see its saved state.")
            if meeting.get("googleMeetUrl") != url:
                raise conflict("The Meet link changed. Please join again.")
            meeting["transcription"] = {
                "id": session_id, "status": "starting", "nativeMeetingId": native,
                "startedAt": now, "updatedAt": now, "segmentIds": [],
                "polling": True, "attempted": False, "failures": 0,
                "leaseUntil": now + LEASE_SECONDS,
            }
            return meeting
        try:
            self.update(meeting_id, begin)
        except vexa.VexaError:
            saved = self.repository.get(meeting_id)
            if saved.get("transcription", {}).get("status") in ACTIVE:
                return saved
            raise
        owner = meeting_id + ":" + session_id
        attempted = False
        confirmed_bot = None
        try:
            if not self.repository.claim_transcription("link-" + native, owner):
                raise conflict("Another Synq meeting is transcribing this Meet link. End that session first.")
            # Durable intent precedes POST. A timeout/crash must never re-send it.
            self.change(meeting_id, session_id, attempted=True)
            attempted = True
            bot = self.provider.join_meeting({"meetingUrl": url})
            # Permanent record binding prevents an old Vexa record being reused.
            if not self.repository.claim_transcription("record-" + str(bot["id"]), owner):
                raise conflict("Vexa returned a record belonging to another session. No transcript was attached.")
            confirmed_bot = bot["id"]
            return self.change(meeting_id, session_id, botId=bot["id"],
                               status="starting", leaseUntil=0, nextPollAt=0)
        except Exception as exc:
            if isinstance(exc, vexa.VexaError) and exc.safe_to_retry:
                attempted = False
            message = (str(exc) if isinstance(exc, MeetingError) else
                       "Transcription could not be started or saved. No automatic bot retry was sent.")
            if confirmed_bot is not None:
                # If persisting the successful spawn fails, best-effort stop the
                # exact confirmed bot. Never leave an acknowledged bot running
                # merely because its Cosmos response could not be committed.
                try:
                    self.provider.stop_session(confirmed_bot, native)
                except Exception:
                    pass
            if attempted:
                message += " The start outcome needs review before another bot can be requested."
            try:
                self.change(meeting_id, session_id, error=message,
                            status="stopping" if confirmed_bot is not None else "error", polling=confirmed_bot is not None, leaseUntil=0, attempted=attempted,
                            **({"botId": confirmed_bot, "stopRequested": True, "stopRequestedAt": now} if confirmed_bot is not None else {}))
                if not attempted:
                    self.repository.release_transcription("link-" + native, owner)
            except Exception:
                logging.error("Unable to persist transcription start failure for %s", meeting_id)
            raise vexa.VexaError(message) from None

    def change(self, meeting_id, session_id, **values):
        def apply(meeting):
            state = meeting.get("transcription", {})
            if state.get("id") != session_id:
                raise conflict("The transcription session changed. Refresh this meeting.")
            state.update(values, updatedAt=self.clock())
            return meeting
        return self.update(meeting_id, apply)

    def end(self, meeting_id):
        def request_stop(meeting):
            state = meeting.get("transcription", {})
            if not state or state.get("status") == "completed" or state.get("terminal"):
                return meeting
            if not state.get("botId"):
                raise conflict("The bot has not been confirmed yet. Refresh shortly. If the start failed, its outcome must be checked before retrying.")
            if state.get("stopRequested") and not state.get("error"):
                return meeting
            state.update(status="stopping", stopRequested=True, polling=True,
                         stopRequestedAt=self.clock(), failures=0, nextPollAt=0, error="")
            return meeting
        self.update(meeting_id, request_stop)
        # One bounded step gives immediate feedback. A timer drains delayed finals.
        self.poll(meeting_id)
        return self.repository.get(meeting_id)

    def poll(self, meeting_id):
        now, lease_id = self.clock(), str(uuid4())
        def claim(meeting):
            state = meeting.get("transcription", {})
            if (not state.get("polling") or state.get("leaseUntil", 0) > now
                    or state.get("nextPollAt", 0) > now):
                raise conflict("Transcription is being checked by another worker.")
            state.update(leaseId=lease_id, leaseUntil=now + LEASE_SECONDS)
            return meeting
        try:
            meeting = self.update(meeting_id, claim)
        except vexa.VexaError:
            return
        state = meeting["transcription"]
        session_id = state["id"]
        try:
            if not state.get("botId"):
                raise vexa.VexaError("The start request was interrupted before its bot could be confirmed. It will not be repeated automatically.")
            data = self.provider.get_session(state["botId"], state["nativeMeetingId"])
            stop = state.get("stopRequested") or now - state["startedAt"] >= MAX_SESSION_SECONDS
            if stop and data["status"] not in TERMINAL and not state.get("stopSent"):
                # Native-key DELETE is safe only after checking the latest record,
                # while the cross-meeting link reservation is still held.
                self.provider.stop_session(state["botId"], state["nativeMeetingId"])
                self.change(meeting_id, session_id, stopSent=True, stopRequested=True,
                            stopRequestedAt=state.get("stopRequestedAt", now), status="stopping")
                data = self.provider.get_session(state["botId"], state["nativeMeetingId"])
            if stop and data["status"] not in TERMINAL and now - state.get("stopRequestedAt", now) > 300:
                raise vexa.VexaError("Vexa has not confirmed the bot stopped. Use End transcription to check again.")
            def save(current):
                current_state = current["transcription"]
                if current_state.get("leaseId") != lease_id or current_state["id"] != session_id:
                    raise conflict("The transcription polling lease expired.")
                seen = set(current_state["segmentIds"])
                lines = current.setdefault("transcript", [])
                added = False
                for segment in data["segments"]:
                    if segment["id"] in seen:
                        continue
                    seen.add(segment["id"])
                    current_state["segmentIds"].append(segment["id"])
                    name = segment["speaker"] or "Unknown speaker"
                    speaker = next((p for p in current["participants"] if p["name"].casefold() == name.casefold()), None)
                    if speaker is None:
                        speaker = {"id": "vexa-" + hashlib.sha256((session_id + name).encode()).hexdigest()[:20],
                                   "name": name, "color": "#547565"}
                    lines.append({"timestamp": segment["timestamp"], "text": segment["text"], "speaker": speaker})
                    added = True
                current_state.update(failures=0, error="", updatedAt=now, leaseUntil=0, nextPollAt=now + 10)
                if data["status"] in TERMINAL:
                    # Terminal status can precede the last STT delivery. Drain until
                    # two terminal snapshots are quiet for at least 30 seconds.
                    if added or "terminalSeenAt" not in current_state:
                        current_state["terminalSeenAt"] = now
                    if now - current_state["terminalSeenAt"] >= 30:
                        current_state.update(status="completed" if data["status"] == "completed" else "error",
                                             terminal=True, polling=False)
                        if data["status"] == "failed":
                            current_state["error"] = "Vexa ended this session with an error. Any received transcript is saved."
                    else:
                        current_state["status"] = "stopping"
                else:
                    current_state.pop("terminalSeenAt", None)
                    current_state["status"] = ("stopping" if current_state.get("stopRequested") else
                                               "transcribing" if data["status"] == "active" else "starting")
                return current
            saved = self.update(meeting_id, save)
            if saved["transcription"].get("terminal"):
                self.release(saved)
        except Exception as exc:
            message = str(exc) if isinstance(exc, MeetingError) else "Transcript could not be fetched or saved. Saved transcript is unchanged; Synq will retry."
            def fail(current):
                current_state = current["transcription"]
                if current_state.get("leaseId") != lease_id:
                    return current
                failures = current_state.get("failures", 0) + 1
                paused = failures >= 6 or not current_state.get("botId")
                current_state.update(failures=failures, error=message, leaseUntil=0,
                                     nextPollAt=now + min(300, 10 * 2 ** failures), updatedAt=now)
                if paused:
                    current_state.update(status="error", polling=False)
                    if current_state.get("botId"):
                        current_state["error"] += " Automatic checks paused. Use End transcription to retry safely."
                    elif current_state.get("attempted"):
                        current_state["error"] += " The uncertain start requires review in Vexa before another bot can be requested."
                    else:
                        current_state["error"] = "The start was interrupted before a bot request. Join Meeting can be retried."
                return current
            try:
                failed = self.update(meeting_id, fail)
                if not failed["transcription"].get("attempted"):
                    self.release(failed)
            except Exception:
                # The persisted lease expires; a future timer retries the same
                # record. No cursor is advanced unless transcript and IDs commit.
                logging.error("Unable to persist transcription poll result for %s", meeting_id)

    def release(self, meeting):
        state = meeting["transcription"]
        self.repository.release_transcription("link-" + state["nativeMeetingId"], meeting["id"] + ":" + state["id"])

    def poll_pending(self):
        # Bound each tick to three sessions and 100 seconds. Oldest-first avoids
        # starving sessions. The timer runs independently of any browser window.
        deadline = time.monotonic() + 100
        records = sorted(self.repository.list(), key=lambda m: m.get("transcription", {}).get("updatedAt", 0))
        processed = 0
        for meeting in records:
            state = meeting.get("transcription", {})
            if state.get("terminal"):
                try:
                    self.release(meeting)  # recover a crash between completion and release
                except Exception:
                    logging.error("Unable to release completed transcription for %s", meeting["id"])
            if not state.get("polling") or state.get("nextPollAt", 0) > self.clock() or state.get("leaseUntil", 0) > self.clock():
                continue
            try:
                self.poll(meeting["id"])
            except Exception:
                logging.error("Unable to check transcription for %s", meeting["id"])
            processed += 1
            if processed >= 3 or time.monotonic() >= deadline:
                break
