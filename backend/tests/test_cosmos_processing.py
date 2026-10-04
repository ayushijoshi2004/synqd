"""Exercise the real Cosmos adapter with an offline, durable container double."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from azure.core import MatchConditions
from azure.cosmos import exceptions

from support import REAL_COSMOS_REPOSITORY
from meeting_errors import MeetingWriteConflict
from meeting_service import MeetingService
from test_ai_processing import intelligence, source


class FileContainer:
    """Test-only Cosmos API double. A fresh instance reads the same saved bytes."""
    def __init__(self, path):
        self.path = path
        if not path.exists(): path.write_text("{}")
        self.before_replace = None

    def records(self):
        return json.loads(self.path.read_text())

    def save(self, records):
        self.path.write_text(json.dumps(records))

    def read_all_items(self):
        return list(self.records().values())

    def read_item(self, item, partition_key):
        assert item == partition_key
        try: return self.records()[item]
        except KeyError: raise exceptions.CosmosResourceNotFoundError(status_code=404)

    def create_item(self, body):
        records = self.records()
        if body["id"] in records: raise exceptions.CosmosResourceExistsError(status_code=409)
        records[body["id"]] = {**deepcopy(body), "_etag": "1"}
        self.save(records)
        return records[body["id"]]

    def replace_item(self, item, body, *, etag, match_condition):
        assert match_condition == MatchConditions.IfNotModified
        if self.before_replace: self.before_replace(body)
        records = self.records()
        if records[item]["_etag"] != etag:
            raise exceptions.CosmosHttpResponseError(status_code=412)
        records[item] = {**deepcopy(body), "_etag": str(int(etag) + 1)}
        self.save(records)
        return records[item]

    def delete_item(self, item, partition_key):
        assert item == partition_key
        records = self.records()
        del records[item]
        self.save(records)


class CosmosProcessingTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "container.json"
        self.repo = self.repository()
        self.repo.create(source())
        self.provider = Mock()
        self.provider.analyze.return_value = intelligence()
        self.service = MeetingService(self.repo, self.provider)

    def repository(self):
        repository = REAL_COSMOS_REPOSITORY.__new__(REAL_COSMOS_REPOSITORY)
        repository.container = FileContainer(self.path)
        return repository

    def test_results_jira_and_agenda_survive_fresh_adapter_and_service(self):
        processed = self.service.process("ai-test")
        jira = Mock()
        jira.create_task.return_value = {"key": "KAN-55", "url": "https://jira.example.invalid/browse/KAN-55"}
        self.service.create_jira_issue("ai-test", processed["actionItems"][-1]["id"], jira)
        expected = self.service.get("ai-test")
        restarted = MeetingService(self.repository(), self.provider)
        self.assertEqual(restarted.get("ai-test"), expected)
        self.assertEqual(restarted.list()[0]["agendaEntries"][0]["completed"], True)
        self.assertEqual(restarted.list()[0]["actionItems"][-1]["jiraIssueKey"], "KAN-55")
        self.assertNotIn("_etag", restarted.get("ai-test"))
        restarted.dismiss_follow_up("ai-test", expected["followUps"][0]["id"])
        self.assertEqual(MeetingService(self.repository()).get("ai-test")["followUps"][0]["status"], "dismissed")

    def test_concurrent_jira_write_during_commit_is_preserved_on_retry(self):
        def racing_write(body):
            if body["aiStatus"] != "processed": return
            self.repo.container.before_replace = None
            records = self.repo.container.records()
            stored = records["ai-test"]
            stored["actionItems"][0]["jiraIssueKey"] = "KAN-88"
            stored["_etag"] = str(int(stored["_etag"]) + 1)
            self.repo.container.save(records)
        self.repo.container.before_replace = racing_write
        processed = self.service.process("ai-test")
        self.assertEqual(processed["actionItems"][0]["jiraIssueKey"], "KAN-88")
        self.assertEqual(processed["aiStatus"], "processed")
        self.provider.analyze.assert_called_once()

    def test_stale_source_write_cleans_up_unsuccessful_approval(self):
        proposal = self.service.process("ai-test")["followUps"][0]
        def racing_write(body):
            self.repo.container.before_replace = None
            records = self.repo.container.records()
            records["ai-test"]["title"] = "Changed concurrently"
            records["ai-test"]["_etag"] = str(int(records["ai-test"]["_etag"]) + 1)
            self.repo.container.save(records)
        self.repo.container.before_replace = racing_write
        with self.assertRaises(MeetingWriteConflict):
            self.service.approve_follow_up("ai-test", proposal["id"], {"date": "2026-10-09", "startTime": "14:00", "endTime": "15:00", "participants": source()["participants"]})
        self.assertEqual(len(self.repo.list()), 1)
        self.assertEqual(self.repo.get("ai-test")["followUps"][0]["status"], "suggested")
        self.assertEqual(self.repo.get("ai-test")["title"], "Changed concurrently")
