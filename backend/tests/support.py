"""Import before function_app: keeps tests off real Cosmos and Jira.

function_app builds a CosmosMeetingRepository at import time. Tests swap that
class for the in-memory repository so no credentials or network are needed.
"""

import os

import cosmos_meeting_repository
from meeting_repository import InMemoryMeetingRepository

# Keep the real adapter available for offline Cosmos contract tests.
REAL_COSMOS_REPOSITORY = cosmos_meeting_repository.CosmosMeetingRepository

for name in ("COSMOS_ENDPOINT", "COSMOS_KEY", "COSMOS_DATABASE", "COSMOS_CONTAINER"):
    os.environ.setdefault(name, "test")


class _TestRepository(InMemoryMeetingRepository):
    def __init__(self, **_connection_settings):
        super().__init__()


cosmos_meeting_repository.CosmosMeetingRepository = _TestRepository
