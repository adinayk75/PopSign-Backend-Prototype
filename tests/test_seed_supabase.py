import math

from scripts.seed_supabase import build_rows, load_catalog
from src.embeddings import EMBEDDING_DIMENSIONS, HashingEmbeddingProvider


def test_seed_rows_are_complete_and_versioned():
    provider = HashingEmbeddingProvider()
    rows = build_rows(load_catalog(), provider)

    assert len(rows["words"]) == 3
    assert len(rows["sign_senses"]) == 6
    assert len(rows["context_phrases"]) == 24
    assert len(rows["phrase_embeddings"]) == 24
    assert all(item["dimensions"] == EMBEDDING_DIMENSIONS for item in rows["phrase_embeddings"])
    assert all(item["model_name"] == provider.model_name for item in rows["phrase_embeddings"])
    assert all(len(item["source_hash"]) == 64 for item in rows["phrase_embeddings"])


def test_seed_embeddings_are_normalized():
    rows = build_rows(load_catalog(), HashingEmbeddingProvider())
    for row in rows["phrase_embeddings"]:
        norm = sum(value * value for value in row["embedding"])
        assert math.isclose(norm, 1.0, rel_tol=1e-9)
