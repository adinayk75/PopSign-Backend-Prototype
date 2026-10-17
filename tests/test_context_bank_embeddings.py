import math

from src.context_bank import build_import_payload
from src.context_bank_embeddings import build_embedding_plan, build_embedding_rows
from src.embeddings import EMBEDDING_DIMENSIONS, HashingEmbeddingProvider
from tests.test_context_bank_import import sample_bank


def test_embedding_plan_has_one_vector_per_word_phrase():
    payload = build_import_payload(sample_bank())
    provider = HashingEmbeddingProvider()
    plan = build_embedding_plan(payload, provider)

    assert len(plan.word_phrases) == payload.summary["word_phrases"]
    assert plan.model_row["dimensions"] == EMBEDDING_DIMENSIONS
    assert plan.model_row["lifecycle_status"] == "demo"


def test_embedding_rows_are_versioned_hashed_and_normalized():
    payload = build_import_payload(sample_bank())
    provider = HashingEmbeddingProvider()
    plan = build_embedding_plan(payload, provider)
    rows = build_embedding_rows(
        plan.word_phrases,
        provider,
        plan.model_row["id"],
    )

    assert len(rows) == payload.summary["word_phrases"]
    assert all(len(row["source_hash"]) == 64 for row in rows)
    assert all(row["embedding_model_id"] == plan.model_row["id"] for row in rows)
    for row in rows:
        norm = sum(value * value for value in row["embedding"])
        assert math.isclose(norm, 1.0, rel_tol=1e-9)
