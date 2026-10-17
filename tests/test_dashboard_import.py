from __future__ import annotations

import csv
import json
from pathlib import Path

from src.context_bank import build_import_payload
from src.dashboard_import import (
    DASHBOARD_TABLE_ORDER,
    export_dashboard_csv_bundle,
    mark_dashboard_table_complete,
)
from tests.test_context_bank_import import sample_bank


def test_dashboard_bundle_preserves_every_payload_row(tmp_path: Path) -> None:
    payload = build_import_payload(sample_bank())
    manifest_path = export_dashboard_csv_bundle(payload, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["table_order"] == list(DASHBOARD_TABLE_ORDER)
    assert manifest["workbook_sha256"] == payload.workbook_sha256
    for table in DASHBOARD_TABLE_ORDER:
        csv_path = tmp_path / manifest["files"][table]
        with csv_path.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        assert len(rows) == len(payload.tables[table])


def test_dashboard_csv_serializes_json_booleans_and_nulls(tmp_path: Path) -> None:
    payload = build_import_payload(sample_bank())
    manifest_path = export_dashboard_csv_bundle(payload, tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    variant_path = tmp_path / manifest["files"]["popsign_sign_variants"]
    with variant_path.open(encoding="utf-8", newline="") as source:
        variant = next(csv.DictReader(source))

    assert json.loads(variant["source_statuses"])
    assert variant["is_active"] in {"true", "false"}
    assert variant["sense_label"] == ""


def test_dashboard_manifest_marks_tables_idempotently(tmp_path: Path) -> None:
    payload = build_import_payload(sample_bank())
    manifest_path = export_dashboard_csv_bundle(payload, tmp_path)

    for table in DASHBOARD_TABLE_ORDER:
        mark_dashboard_table_complete(manifest_path, table)
        mark_dashboard_table_complete(manifest_path, table)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["completed_tables"] == list(DASHBOARD_TABLE_ORDER)
    assert manifest["status"] == "completed"
