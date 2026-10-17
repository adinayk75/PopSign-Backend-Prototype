import csv
import json
from pathlib import Path

import pytest

from src.context_bank import build_import_payload
from src.context_bank_embeddings import build_embedding_plan
from src.embedding_export import (
    export_embedding_csv_bundle,
    mark_embedding_batch_uploaded,
    mark_embedding_model_uploaded,
)
from src.embeddings import EMBEDDING_DIMENSIONS, EmbeddingProvider
from tests.test_context_bank_import import sample_bank


class RecordingSemanticProvider(EmbeddingProvider):
    model_name = "test/semantic-768"
    model_version = "hf-test-revision"
    provider_kind = "sentence_transformers"
    prompt_template = 'Meaning of "{target_word}" in this sentence: {context_text}'

    def __init__(self) -> None:
        self.batch_lengths: list[int] = []

    def embed(self, text: str, target_word: str | None = None) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        vector[0] = 1.0
        return vector

    def embed_many(
        self,
        items,
    ) -> list[list[float]]:
        materialized = list(items)
        self.batch_lengths.append(len(materialized))
        return [self.embed(text, target) for text, target in materialized]


def test_embedding_export_is_complete_batched_and_resumable(tmp_path: Path):
    payload = build_import_payload(sample_bank())
    provider = RecordingSemanticProvider()
    plan = build_embedding_plan(payload, provider)
    manifest_path = export_embedding_csv_bundle(
        payload,
        plan,
        provider,
        tmp_path,
        batch_size=2,
        progress=lambda _: None,
    )

    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "generated"
    assert manifest["generated_rows"] == len(plan.word_phrases)
    assert sum(batch["count"] for batch in manifest["batches"]) == len(
        plan.word_phrases
    )
    assert provider.batch_lengths == [
        min(2, len(plan.word_phrases) - start)
        for start in range(0, len(plan.word_phrases), 2)
    ]

    first_batch = tmp_path / manifest["batches"][0]["filename"]
    with first_batch.open(newline="", encoding="utf-8") as source:
        row = next(csv.DictReader(source))
    assert row["embedding"].startswith("[1,")
    assert len(row["embedding"].strip("[]").split(",")) == EMBEDDING_DIMENSIONS

    resumed_provider = RecordingSemanticProvider()
    export_embedding_csv_bundle(
        payload,
        build_embedding_plan(payload, resumed_provider),
        resumed_provider,
        tmp_path,
        batch_size=2,
        progress=lambda _: None,
    )
    assert resumed_provider.batch_lengths == []


def test_embedding_export_tracks_confirmed_dashboard_uploads(tmp_path: Path):
    payload = build_import_payload(sample_bank())
    provider = RecordingSemanticProvider()
    manifest_path = export_embedding_csv_bundle(
        payload,
        build_embedding_plan(payload, provider),
        provider,
        tmp_path,
        batch_size=100,
        progress=lambda _: None,
    )

    mark_embedding_model_uploaded(manifest_path)
    mark_embedding_batch_uploaded(manifest_path, 1)
    manifest = json.loads(manifest_path.read_text())

    assert manifest["model_uploaded"] is True
    assert manifest["uploaded_rows"] == manifest["total_embeddings"]
    assert manifest["status"] == "completed"


def test_embedding_export_rejects_changed_model_file_on_resume(tmp_path: Path):
    payload = build_import_payload(sample_bank())
    provider = RecordingSemanticProvider()
    plan = build_embedding_plan(payload, provider)
    manifest_path = export_embedding_csv_bundle(
        payload,
        plan,
        provider,
        tmp_path,
        batch_size=100,
        progress=lambda _: None,
    )
    manifest = json.loads(manifest_path.read_text())
    (tmp_path / manifest["model_file"]).write_text("changed\n")

    with pytest.raises(RuntimeError, match="model export is missing or changed"):
        export_embedding_csv_bundle(
            payload,
            plan,
            provider,
            tmp_path,
            batch_size=100,
            progress=lambda _: None,
        )
