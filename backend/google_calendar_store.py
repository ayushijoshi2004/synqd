"""Encrypted integration data in the existing Cosmos container, never meeting data."""

import json
from azure.cosmos import exceptions
from azure.core import MatchConditions
from cryptography.fernet import Fernet

PRIVATE_PREFIX = "__synq_google_"


class GoogleCalendarStore:
    def __init__(self, container, encryption_key):
        self.container = container
        self.cipher = Fernet(encryption_key.encode())

    def get(self, key):
        try:
            item = self.container.read_item(item=PRIVATE_PREFIX + key, partition_key=PRIVATE_PREFIX + key)
        except exceptions.CosmosResourceNotFoundError:
            return None
        return json.loads(self.cipher.decrypt(item["encrypted"].encode()))

    def put(self, key, value):
        self.container.upsert_item({
            "id": PRIVATE_PREFIX + key,
            "encrypted": self.cipher.encrypt(json.dumps(value).encode()).decode(),
        })

    def consume(self, key):
        """Consume OAuth state once, including across concurrent Functions workers."""
        try:
            item = self.container.read_item(item=PRIVATE_PREFIX + key, partition_key=PRIVATE_PREFIX + key)
            self.container.delete_item(item=item["id"], partition_key=item["id"],
                                       etag=item["_etag"], match_condition=MatchConditions.IfNotModified)
            return json.loads(self.cipher.decrypt(item["encrypted"].encode()))
        except exceptions.CosmosResourceNotFoundError:
            return None
        except exceptions.CosmosHttpResponseError as exc:
            if exc.status_code == 412:
                return None
            raise
