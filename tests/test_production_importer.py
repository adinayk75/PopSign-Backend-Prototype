from pathlib import Path

import pytest

from src.context_bank import build_import_payload
from src.supabase_import import SupabaseContextBankImporter
from tests.test_context_bank_import import sample_bank


class FakeResponse:
    data = []


class FakeQuery:
    def __init__(self, client, table, action, payload):
        self.client = client
        self.table = table
        self.action = action
        self.payload = payload
        self.filters = []

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        self.client.calls.append(
            {
                "table": self.table,
                "action": self.action,
                "payload": self.payload,
                "filters": self.filters,
            }
        )
        if (
            self.action == "upsert"
            and self.table == self.client.fail_table
            and sum(
                call["action"] == "upsert" and call["table"] == self.table
                for call in self.client.calls
            )
            == self.client.fail_on_upsert_number
        ):
            raise RuntimeError("simulated interruption")
        return FakeResponse()


class FakeTable:
    def __init__(self, client, name):
        self.client = client
        self.name = name

    def upsert(self, rows, on_conflict):
        return FakeQuery(
            self.client,
            self.name,
            "upsert",
            {"rows": rows, "on_conflict": on_conflict},
        )

    def update(self, values):
        return FakeQuery(self.client, self.name, "update", values)


class FakeClient:
    def __init__(self, fail_table=None, fail_on_upsert_number=0):
        self.calls = []
        self.fail_table = fail_table
        self.fail_on_upsert_number = fail_on_upsert_number

    def table(self, name):
        return FakeTable(self, name)


def test_import_resumes_after_the_last_successful_batch(tmp_path: Path):
    payload = build_import_payload(sample_bank())
    checkpoint = tmp_path / "resume.json"
    interrupted_client = FakeClient(
        fail_table="popsign_words",
        fail_on_upsert_number=2,
    )
    importer = SupabaseContextBankImporter(
        interrupted_client,
        batch_size=1,
        progress=lambda _: None,
    )

    with pytest.raises(RuntimeError, match="simulated interruption"):
        importer.import_payload(payload, checkpoint)

    resumed_client = FakeClient()
    result = SupabaseContextBankImporter(
        resumed_client,
        batch_size=1,
        progress=lambda _: None,
    ).import_payload(payload, checkpoint)

    assert result.resumed is True
    assert result.uploaded_in_this_run["popsign_words"] == 1
    word_upserts = [
        call
        for call in resumed_client.calls
        if call["action"] == "upsert" and call["table"] == "popsign_words"
    ]
    assert len(word_upserts) == 1
    assert checkpoint.exists()


def test_completed_import_can_be_rerun_without_duplicate_batches(tmp_path: Path):
    payload = build_import_payload(sample_bank())
    checkpoint = tmp_path / "complete.json"
    first = SupabaseContextBankImporter(
        FakeClient(), batch_size=2, progress=lambda _: None
    )
    first.import_payload(payload, checkpoint)

    second_client = FakeClient()
    result = SupabaseContextBankImporter(
        second_client, batch_size=2, progress=lambda _: None
    ).import_payload(payload, checkpoint)

    assert result.resumed is True
    assert all(count == 0 for count in result.uploaded_in_this_run.values())
