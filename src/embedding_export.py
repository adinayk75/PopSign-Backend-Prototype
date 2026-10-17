from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from src.context_bank import ImportPayload, SCHEMA_VERSION
from src.context_bank_embeddings import (
    EmbeddingPlan,
    build_embedding_rows,
)
from src.embeddings import EmbeddingProvider
from src.supabase_import import batch_ranges


MODEL_FILENAME = "popsign_embedding_models.csv"
EMBEDDING_FIELDS = (
    "word_phrase_id",
    "embedding_model_id",
    "dimensions",
    "source_hash",
    "embedding",
)


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in values) + "]"


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...] | list[str],
    rows: list[dict[str, Any]],
) -> str:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=fieldnames,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
    return _sha256(path)


def _identity(
    payload: ImportPayload,
    plan: EmbeddingPlan,
    provider: EmbeddingProvider,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "workbook_sha256": payload.workbook_sha256,
        "import_run_id": payload.import_run_id,
        "embedding_model_id": plan.model_row["id"],
        "model_name": provider.model_name,
        "model_version": provider.model_version,
        "dimensions": provider.dimensions,
        "prompt_template": provider.prompt_template,
        "total_embeddings": len(plan.word_phrases),
    }


def _load_resumable_manifest(
    manifest_path: Path,
    expected_identity: dict[str, Any],
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_identity = {key: manifest.get(key) for key in expected_identity}
    if actual_identity != expected_identity:
        raise RuntimeError(
            "The embedding export belongs to a different workbook or model. "
            "Choose a different output directory or pass --restart."
        )

    model_path = manifest_path.parent / manifest["model_file"]
    if (
        not model_path.exists()
        or _sha256(model_path) != manifest["model_file_sha256"]
    ):
        raise RuntimeError(
            f"Embedding model export is missing or changed: {model_path.name}"
        )

    generated_rows = 0
    for index, batch in enumerate(manifest.get("batches", []), start=1):
        if batch["index"] != index or batch["start"] != generated_rows:
            raise RuntimeError("Embedding export manifest has a non-contiguous batch list.")
        batch_path = manifest_path.parent / batch["filename"]
        if not batch_path.exists() or _sha256(batch_path) != batch["sha256"]:
            raise RuntimeError(
                f"Embedding export batch is missing or changed: {batch_path.name}"
            )
        generated_rows = int(batch["end"])

    if generated_rows != int(manifest.get("generated_rows", 0)):
        raise RuntimeError("Embedding export manifest row count is inconsistent.")
    return manifest


def export_embedding_csv_bundle(
    payload: ImportPayload,
    plan: EmbeddingPlan,
    provider: EmbeddingProvider,
    output_dir: Path,
    *,
    batch_size: int = 1000,
    restart: bool = False,
    progress: Callable[[str], None] = print,
) -> Path:
    """Generate private, resumable CSV batches for a dashboard Supabase import."""

    if batch_size < 1 or batch_size > 5000:
        raise ValueError("Embedding export batch size must be between 1 and 5000.")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    expected_identity = _identity(payload, plan, provider)

    if restart:
        for path in output_dir.glob("popsign_phrase_embeddings_*.csv"):
            path.unlink()
        manifest_path.unlink(missing_ok=True)

    if manifest_path.exists():
        manifest = _load_resumable_manifest(manifest_path, expected_identity)
    else:
        model_row = {
            key: ("true" if value is True else "false" if value is False else value)
            for key, value in plan.model_row.items()
        }
        model_path = output_dir / MODEL_FILENAME
        model_sha256 = _write_csv(
            model_path,
            list(plan.model_row),
            [model_row],
        )
        manifest = {
            **expected_identity,
            "generated_at": datetime.now(UTC).isoformat(),
            "batch_size": batch_size,
            "model_file": MODEL_FILENAME,
            "model_file_sha256": model_sha256,
            "model_uploaded": False,
            "generated_rows": 0,
            "uploaded_rows": 0,
            "batches": [],
            "status": "prepared",
        }
        _atomic_json_write(manifest_path, manifest)

    completed = int(manifest["generated_rows"])
    total = len(plan.word_phrases)
    if completed > total:
        raise RuntimeError(
            f"Export says {completed} embeddings exist, but the plan contains {total}."
        )

    for start, end in batch_ranges(total, batch_size, start=completed):
        embedding_rows = build_embedding_rows(
            plan.word_phrases[start:end],
            provider,
            plan.model_row["id"],
        )
        csv_rows = [
            {
                **{key: row[key] for key in EMBEDDING_FIELDS if key != "embedding"},
                "embedding": _vector_literal(row["embedding"]),
            }
            for row in embedding_rows
        ]
        filename = f"popsign_phrase_embeddings_{start + 1:05d}_{end:05d}.csv"
        file_sha256 = _write_csv(
            output_dir / filename,
            list(EMBEDDING_FIELDS),
            csv_rows,
        )
        manifest["batches"].append(
            {
                "index": len(manifest["batches"]) + 1,
                "start": start,
                "end": end,
                "count": end - start,
                "filename": filename,
                "sha256": file_sha256,
                "uploaded": False,
            }
        )
        manifest["generated_rows"] = end
        manifest["status"] = "generated" if end == total else "generating"
        _atomic_json_write(manifest_path, manifest)
        progress(f"Generated embeddings: {end}/{total}.")

    return manifest_path


def mark_embedding_model_uploaded(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["model_uploaded"] = True
    manifest["status"] = "uploading"
    _atomic_json_write(manifest_path, manifest)


def mark_embedding_batch_uploaded(manifest_path: Path, batch_index: int) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    batches = manifest["batches"]
    if batch_index < 1 or batch_index > len(batches):
        raise ValueError(f"Unknown embedding batch index: {batch_index}")
    batches[batch_index - 1]["uploaded"] = True
    manifest["uploaded_rows"] = sum(
        int(batch["count"]) for batch in batches if batch["uploaded"]
    )
    fully_uploaded = (
        manifest.get("model_uploaded")
        and manifest["uploaded_rows"] == manifest["total_embeddings"]
    )
    manifest["status"] = "completed" if fully_uploaded else "uploading"
    _atomic_json_write(manifest_path, manifest)
