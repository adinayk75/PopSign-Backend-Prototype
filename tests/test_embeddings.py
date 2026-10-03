import math

from src.embeddings import EMBEDDING_DIMENSIONS, HashingEmbeddingProvider, cosine_similarity


def test_hashing_embeddings_are_normalized_and_deterministic():
    provider = HashingEmbeddingProvider()
    first = provider.embed("Maya can cook dinner.", "can")
    second = provider.embed("Maya can cook dinner.", "can")

    assert first == second
    assert len(first) == EMBEDDING_DIMENSIONS
    assert math.isclose(sum(value * value for value in first), 1.0, rel_tol=1e-9)


def test_context_changes_embedding_direction():
    provider = HashingEmbeddingProvider()
    ability = provider.embed("Maya can cook dinner.", "can")
    container = provider.embed("She opened a can of soup.", "can")

    assert cosine_similarity(ability, container) < 0.5
