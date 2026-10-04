"""Storage contract and process-local adapter. No Azure SDK or credentials."""

from collections.abc import Callable, Iterable
from copy import deepcopy
from threading import RLock
from typing import Protocol

from meeting_errors import MeetingAlreadyExists, MeetingNotFound
from meeting_model import Meeting


class MeetingRepository(Protocol):
    def list(self) -> list[Meeting]: ...
    def get(self, meeting_id: str) -> Meeting: ...
    def create(self, meeting: Meeting) -> Meeting: ...
    def update(self, meeting_id: str, change: Callable[[Meeting], Meeting]) -> Meeting: ...
    def delete(self, meeting_id: str) -> None: ...
    def claim_transcription(self, key: str, owner: str) -> bool: ...
    def release_transcription(self, key: str, owner: str) -> None: ...


class InMemoryMeetingRepository:
    """Copy-on-read/write records; serialized mutations within one worker.

    update() applies the service's validation to the latest record while holding
    the lock. A future shared adapter can use optimistic concurrency internally
    to preserve this operation without changing any route handlers.
    """

    def __init__(self, seed: Iterable[Meeting] = ()):
        self._records: dict[str, Meeting] = {}
        self._lock = RLock()
        self._transcription_claims: dict[str, str] = {}
        for meeting in seed:
            self.create(meeting)

    def list(self) -> list[Meeting]:
        with self._lock:
            return deepcopy(list(self._records.values()))

    def get(self, meeting_id: str) -> Meeting:
        with self._lock:
            if meeting_id not in self._records:
                raise MeetingNotFound()
            return deepcopy(self._records[meeting_id])

    def create(self, meeting: Meeting) -> Meeting:
        with self._lock:
            if meeting["id"] in self._records:
                raise MeetingAlreadyExists()
            self._records[meeting["id"]] = deepcopy(meeting)
            return deepcopy(meeting)

    def update(self, meeting_id: str, change: Callable[[Meeting], Meeting]) -> Meeting:
        with self._lock:
            current = self.get(meeting_id)
            updated = change(current)
            self._records[meeting_id] = deepcopy(updated)
            return deepcopy(updated)

    def delete(self, meeting_id: str) -> None:
        with self._lock:
            if meeting_id not in self._records:
                raise MeetingNotFound()
            del self._records[meeting_id]

    def claim_transcription(self, key: str, owner: str) -> bool:
        with self._lock:
            previous = self._transcription_claims.get(key)
            if previous is not None and previous != owner:
                return False
            self._transcription_claims[key] = owner
            return True

    def release_transcription(self, key: str, owner: str) -> None:
        with self._lock:
            if self._transcription_claims.get(key) == owner:
                del self._transcription_claims[key]
