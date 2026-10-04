from collections.abc import Callable
from copy import deepcopy

from azure.cosmos import CosmosClient, exceptions
from azure.core import MatchConditions

from meeting_errors import MeetingAlreadyExists, MeetingNotFound, MeetingWriteConflict
from meeting_model import Meeting

PRIVATE_PREFIX = ("__synq_google_", "__synq_vexa_")


COSMOS_METADATA_FIELDS = {
    "_rid",
    "_self",
    "_etag",
    "_attachments",
    "_ts",
}


def clean_item(item: dict) -> dict:
    return {
        key: value
        for key, value in item.items()
        if key not in COSMOS_METADATA_FIELDS
    }


class CosmosMeetingRepository:
    def __init__(
        self,
        endpoint: str,
        key: str,
        database_name: str,
        container_name: str,
    ):
        client = CosmosClient(endpoint, credential=key)
        database = client.get_database_client(database_name)
        self.container = database.get_container_client(container_name)

    def list(self) -> list[Meeting]:
        items = self.container.read_all_items()
        return [
            deepcopy(clean_item(item))
            for item in items
            if not item["id"].startswith(PRIVATE_PREFIX)
        ]

    def get(self, meeting_id: str) -> Meeting:
        if meeting_id.startswith(PRIVATE_PREFIX):
            raise MeetingNotFound()
        try:
            item = self.container.read_item(
                item=meeting_id,
                partition_key=meeting_id,
            )
            return deepcopy(clean_item(item))
        except exceptions.CosmosResourceNotFoundError:
            raise MeetingNotFound()

    def create(self, meeting: Meeting) -> Meeting:
        if meeting["id"].startswith(PRIVATE_PREFIX):
            raise MeetingAlreadyExists()
        try:
            created = self.container.create_item(
                body=meeting,
            )
            return deepcopy(clean_item(created))
        except exceptions.CosmosResourceExistsError:
            raise MeetingAlreadyExists()

    def update(
        self,
        meeting_id: str,
        change: Callable[[Meeting], Meeting],
    ) -> Meeting:
        if meeting_id.startswith(PRIVATE_PREFIX):
            raise MeetingNotFound()
        try:
            stored = self.container.read_item(item=meeting_id, partition_key=meeting_id)
            updated = change(deepcopy(clean_item(stored)))
            replaced = self.container.replace_item(
                item=meeting_id, body=updated,
                etag=stored["_etag"], match_condition=MatchConditions.IfNotModified,
            )
            return deepcopy(clean_item(replaced))
        except exceptions.CosmosResourceNotFoundError:
            raise MeetingNotFound()
        except exceptions.CosmosHttpResponseError as exc:
            if exc.status_code == 412:
                # Never repeat a callback here: follow-up approval has a create
                # side effect. The service may retry only its pure callbacks.
                raise MeetingWriteConflict() from exc
            raise

    def delete(self, meeting_id: str) -> None:
        if meeting_id.startswith(PRIVATE_PREFIX):
            raise MeetingNotFound()
        try:
            self.container.delete_item(
                item=meeting_id,
                partition_key=meeting_id,
            )
        except exceptions.CosmosResourceNotFoundError:
            raise MeetingNotFound()

    def claim_transcription(self, key: str, owner: str) -> bool:
        """Atomic private claims in the existing container, partition key /id.

        Link claims are released after final draining. Record claims are retained
        permanently so a provider record cannot attach to a second Synq meeting.
        """
        record_id = "__synq_vexa_" + key
        body = {"id": record_id, "owner": owner, "active": True}
        try:
            self.container.create_item(body=body)
            return True
        except exceptions.CosmosResourceExistsError:
            stored = self.container.read_item(item=record_id, partition_key=record_id)
            if stored.get("active"):
                return stored.get("owner") == owner
            try:
                self.container.replace_item(item=record_id, body=body,
                    etag=stored["_etag"], match_condition=MatchConditions.IfNotModified)
                return True
            except exceptions.CosmosHttpResponseError as exc:
                if exc.status_code == 412:
                    return False
                raise

    def release_transcription(self, key: str, owner: str) -> None:
        record_id = "__synq_vexa_" + key
        try:
            stored = self.container.read_item(item=record_id, partition_key=record_id)
            if stored.get("owner") != owner or not stored.get("active"):
                return
            self.container.replace_item(item=record_id, body={"id": record_id, "owner": owner, "active": False},
                etag=stored["_etag"], match_condition=MatchConditions.IfNotModified)
        except exceptions.CosmosResourceNotFoundError:
            return
        except exceptions.CosmosHttpResponseError as exc:
            if exc.status_code != 412:
                raise
