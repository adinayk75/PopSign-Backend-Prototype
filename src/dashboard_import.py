from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.context_bank import ImportPayload, SCHEMA_VERSION
from src.supabase_import import TABLE_ORDER


DASHBOARD_TABLE_ORDER = ("popsign_import_runs", *TABLE_ORDER)


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def export_dashboard_csv_bundle(
    payload: ImportPayload,
    output_dir: Path,
) -> Path:
    """Write private, dashboard-importable CSVs plus a resumable manifest."""

    output_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    counts: dict[str, int] = {}

    for table in DASHBOARD_TABLE_ORDER:
        rows = payload.tables[table]
        if not rows:
            raise ValueError(f"Cannot export empty table payload: {table}")

        path = output_dir / f"{table}.csv"
        fieldnames = list(rows[0])
        with path.open("w", encoding="utf-8", newline="") as destination:
            writer = csv.DictWriter(
                destination,
                fieldnames=fieldnames,
                extrasaction="raise",
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})

        files[table] = path.name
        counts[table] = len(rows)

    manifest_path = output_dir / "manifest.json"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "workbook_sha256": payload.workbook_sha256,
        "import_run_id": payload.import_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "table_order": list(DASHBOARD_TABLE_ORDER),
        "files": files,
        "expected_counts": counts,
        "completed_tables": [],
        "status": "prepared",
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def mark_dashboard_table_complete(manifest_path: Path, table: str) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    table_order = manifest["table_order"]
    if table not in table_order:
        raise ValueError(f"Unknown dashboard import table: {table}")

    completed = list(manifest.get("completed_tables", []))
    if table not in completed:
        completed.append(table)
    completed.sort(key=table_order.index)
    manifest["completed_tables"] = completed
    manifest["status"] = (
        "completed" if completed == table_order else "importing"
    )

    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
