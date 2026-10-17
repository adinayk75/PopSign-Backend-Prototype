from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.context_bank import ImportPayload, stable_uuid
from src.embeddings import EmbeddingProvider
from src.supabase_import import CONFLICT_COLUMNS, ImportCheckpoint, batch_ranges


EMBEDDING_TABLE = "popsign_phrase_embeddings"


@dataclass(frozen=True)
class EmbeddingPlan:
    model_row: dict[str, Any]
    word_phrases: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class EmbeddingImportResult:
    embedding_model_id: str
    total_embeddings: int
    uploaded_in_this_run: int
    resumed: bool


def prompt_template(provider: EmbeddingProvider) -> str:
    return provider.prompt_template


def provider_kind(provider: EmbeddingProvider) -> str:
    return provider.provider_kind


def build_embedding_plan(
    payload: ImportPayload,
    provider: EmbeddingProvider,
) -> EmbeddingPlan:
    template = prompt_template(provider)
    model_id = stable_uuid(
        "embedding_model",
        provider.model_name,
        provider.model_version,
        provider.dimensions,
        template,
    )
    model_row = {
        "id": model_id,
        "model_name": provider.model_name,
        "model_version": provider.model_version,
        "provider_kind": provider_kind(provider),
        "dimensions": provider.dimensions,
        "prompt_template": template,
        "normalized": True,
        "lifecycle_status": (
            "demo" if provider_kind(provider) == "hashing_demo" else "candidate"
        ),
    }

    words = {row["id"]: row["word_key"] for row in payload.tables["popsign_words"]}
    phrases = {
        row["id"]: row["context_text"] for row in payload.tables["popsign_phrases"]
    }
    pairs = tuple(
        {
            "word_phrase_id": row["id"],
            "target_word": words[row["word_id"]],
            "context_text": phrases[row["phrase_id"]],
        }
        for row in payload.tables["popsign_word_phrases"]
    )
    return EmbeddingPlan(model_row=model_row, word_phrases=pairs)


def embedding_source_hash(
    provider: EmbeddingProvider,
    target_word: str,
    context_text: str,
) -> str:
    source = {
        "model_name": provider.model_name,
        "model_version": provider.model_version,
        "dimensions": provider.dimensions,
        "prompt_template": prompt_template(provider),
        "target_word": target_word,
        "context_text": context_text,
    }
    encoded = json.dumps(
        source,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_embedding_rows(
    pairs: tuple[dict[str, str], ...] | list[dict[str, str]],
    provider: EmbeddingProvider,
    embedding_model_id: str,
) -> list[dict[str, Any]]:
    vectors = provider.embed_many(
        (pair["context_text"], pair["target_word"]) for pair in pairs
    )
    if len(vectors) != len(pairs):
        raise ValueError(
            f"Expected {len(pairs)} embeddings; received {len(vectors)}."
        )

    rows: list[dict[str, Any]] = []
    for pair, vector in zip(pairs, vectors, strict=True):
        if len(vector) != provider.dimensions:
            raise ValueError(
                f"Expected {provider.dimensions} dimensions; received {len(vector)}."
            )
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("Embedding contains a non-finite value.")
        norm = math.sqrt(sum(value * value for value in vector))
        if not math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5):
            raise ValueError(f"Embedding is not normalized; norm={norm}.")
        rows.append(
            {
                "word_phrase_id": pair["word_phrase_id"],
                "embedding_model_id": embedding_model_id,
                "dimensions": provider.dimensions,
                "source_hash": embedding_source_hash(
                    provider,
                    pair["target_word"],
                    pair["context_text"],
                ),
                "embedding": vector,
            }
        )
    return rows


def validate_embedding_plan(
    plan: EmbeddingPlan,
    provider: EmbeddingProvider,
    *,
    batch_size: int = 25,
    progress: Callable[[str], None] = print,
) -> int:
    total = len(plan.word_phrases)
    for start, end in batch_ranges(total, batch_size):
        build_embedding_rows(
            plan.word_phrases[start:end],
            provider,
            plan.model_row["id"],
        )
        progress(f"Validated embeddings: {end}/{total}.")
    return total


class SupabaseEmbeddingImporter:
    def __init__(
        self,
        client: Any,
        *,
        batch_size: int = 25,
        progress: Callable[[str], None] = print,
    ) -> None:
        if batch_size < 1 or batch_size > 200:
            raise ValueError("Embedding batch size must be between 1 and 200.")
        self.client = client
        self.batch_size = batch_size
        self.progress = progress

    def import_plan(
        self,
        payload: ImportPayload,
        plan: EmbeddingPlan,
        provider: EmbeddingProvider,
        checkpoint_path: Path,
        *,
        restart: bool = False,
    ) -> EmbeddingImportResult:
        model_id = str(plan.model_row["id"])
        checkpoint = ImportCheckpoint(
            checkpoint_path,
            f"{payload.import_run_id}:{model_id}",
            payload.workbook_sha256,
            reset=restart,
        )
        self.client.table("popsign_embedding_models").upsert(
            [plan.model_row],
            on_conflict=CONFLICT_COLUMNS["popsign_embedding_models"],
        ).execute()

        total = len(plan.word_phrases)
        completed = checkpoint.completed(EMBEDDING_TABLE)
        if completed > total:
            raise RuntimeError(
                f"Checkpoint says {completed} embeddings were imported, "
                f"but this plan contains only {total}."
            )

        uploaded = 0
        try:
            for start, end in batch_ranges(total, self.batch_size, start=completed):
                rows = build_embedding_rows(
                    plan.word_phrases[start:end],
                    provider,
                    model_id,
                )
                self.client.table(EMBEDDING_TABLE).upsert(
                    rows,
                    on_conflict=CONFLICT_COLUMNS[EMBEDDING_TABLE],
                ).execute()
                uploaded += len(rows)
                checkpoint.advance(EMBEDDING_TABLE, end)
                self.progress(f"Embeddings: {end}/{total} upserted.")
            checkpoint.finish()
        except Exception:
            checkpoint.fail()
            raise

        return EmbeddingImportResult(
            embedding_model_id=model_id,
            total_embeddings=total,
            uploaded_in_this_run=uploaded,
            resumed=checkpoint.resumed,
        )
