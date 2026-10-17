from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from src.context_bank import ImportPayload, SCHEMA_VERSION


TABLE_ORDER = (
    "popsign_words",
    "popsign_sign_variants",
    "popsign_source_rows",
    "popsign_phrases",
    "popsign_word_phrases",
    "popsign_variant_contexts",
    "popsign_tags",
    "popsign_variant_tags",
)

CONFLICT_COLUMNS = {
    "popsign_import_runs": "id",
    "popsign_words": "id",
    "popsign_sign_variants": "id",
    "popsign_source_rows": "id",
    "popsign_phrases": "id",
    "popsign_word_phrases": "id",
    "popsign_variant_contexts": "id",
    "popsign_tags": "id",
    "popsign_variant_tags": "id",
    "popsign_embedding_models": "id",
    "popsign_phrase_embeddings": "word_phrase_id,embedding_model_id",
}


@dataclass(frozen=True)
class ImportResult:
    import_run_id: str
    table_counts: dict[str, int]
    uploaded_in_this_run: dict[str, int]
    resumed: bool


def batch_ranges(total: int, size: int, start: int = 0) -> Iterable[tuple[int, int]]:
    if size < 1:
        raise ValueError("Batch size must be at least 1.")
    if start < 0 or start > total:
        raise ValueError(f"Invalid batch start {start} for {total} rows.")
    for offset in range(start, total, size):
        yield offset, min(offset + size, total)


class ImportCheckpoint:
    def __init__(
        self,
        path: Path,
        import_run_id: str,
        workbook_sha256: str,
        *,
        reset: bool = False,
    ) -> None:
        self.path = path
        self.import_run_id = import_run_id
        self.workbook_sha256 = workbook_sha256
        self.resumed = False
        self.state: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "import_run_id": import_run_id,
            "workbook_sha256": workbook_sha256,
            "status": "prepared",
            "completed_rows": {},
        }
        if reset and path.exists():
            path.unlink()
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            identity = (
                loaded.get("schema_version"),
                loaded.get("import_run_id"),
                loaded.get("workbook_sha256"),
            )
            expected = (SCHEMA_VERSION, import_run_id, workbook_sha256)
            if identity != expected:
                raise RuntimeError(
                    "The checkpoint belongs to a different schema or workbook. "
                    "Use a different --checkpoint path or pass --restart."
                )
            self.state = loaded
            self.resumed = any(
                int(value) > 0
                for value in loaded.get("completed_rows", {}).values()
            )

    def completed(self, table: str) -> int:
        return int(self.state.get("completed_rows", {}).get(table, 0))

    def advance(self, table: str, completed_rows: int) -> None:
        self.state.setdefault("completed_rows", {})[table] = completed_rows
        self.state["status"] = "importing"
        self.save()

    def finish(self) -> None:
        self.state["status"] = "completed"
        self.save()

    def fail(self) -> None:
        self.state["status"] = "failed"
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


class SupabaseContextBankImporter:
    def __init__(
        self,
        client: Any,
        *,
        batch_size: int = 100,
        progress: Callable[[str], None] = print,
    ) -> None:
        if batch_size < 1 or batch_size > 1000:
            raise ValueError("Batch size must be between 1 and 1000.")
        self.client = client
        self.batch_size = batch_size
        self.progress = progress

    def _upsert(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self.client.table(table).upsert(
            rows,
            on_conflict=CONFLICT_COLUMNS[table],
        ).execute()

    def _update_run(self, import_run_id: str, values: dict[str, Any]) -> None:
        self.client.table("popsign_import_runs").update(values).eq(
            "id", import_run_id
        ).execute()

    def import_payload(
        self,
        payload: ImportPayload,
        checkpoint_path: Path,
        *,
        restart: bool = False,
    ) -> ImportResult:
        checkpoint = ImportCheckpoint(
            checkpoint_path,
            payload.import_run_id,
            payload.workbook_sha256,
            reset=restart,
        )
        uploaded = {table: 0 for table in TABLE_ORDER}
        run_row = dict(payload.tables["popsign_import_runs"][0])
        run_row.update(
            {
                "status": "importing",
                "phase": "base_data",
                "progress": checkpoint.state.get("completed_rows", {}),
                "error_message": None,
                "started_at": datetime.now(UTC).isoformat(),
            }
        )
        self._upsert("popsign_import_runs", [run_row])

        try:
            for table in TABLE_ORDER:
                rows = payload.tables[table]
                completed = checkpoint.completed(table)
                if completed > len(rows):
                    raise RuntimeError(
                        f"Checkpoint says {completed} {table} rows were imported, "
                        f"but this payload contains only {len(rows)}."
                    )
                if completed == len(rows):
                    self.progress(f"{table}: already complete ({len(rows)} rows).")
                    continue

                for start, end in batch_ranges(
                    len(rows), self.batch_size, start=completed
                ):
                    self._upsert(table, rows[start:end])
                    uploaded[table] += end - start
                    checkpoint.advance(table, end)
                    self._update_run(
                        payload.import_run_id,
                        {
                            "status": "importing",
                            "phase": table,
                            "progress": checkpoint.state["completed_rows"],
                            "error_message": None,
                        },
                    )
                    self.progress(f"{table}: {end}/{len(rows)} rows upserted.")

            checkpoint.finish()
            self._update_run(
                payload.import_run_id,
                {
                    "status": "completed",
                    "phase": "base_data_complete",
                    "progress": checkpoint.state["completed_rows"],
                    "error_message": None,
                    "completed_at": datetime.now(UTC).isoformat(),
                },
            )
        except Exception as exc:
            checkpoint.fail()
            try:
                self._update_run(
                    payload.import_run_id,
                    {
                        "status": "failed",
                        "progress": checkpoint.state.get("completed_rows", {}),
                        "error_message": str(exc)[:2000],
                    },
                )
            except Exception:
                pass
            raise

        return ImportResult(
            import_run_id=payload.import_run_id,
            table_counts={table: len(payload.tables[table]) for table in TABLE_ORDER},
            uploaded_in_this_run=uploaded,
            resumed=checkpoint.resumed,
        )
