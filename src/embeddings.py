from __future__ import annotations

import hashlib
import math
import os
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Iterable


TOKEN_RE = re.compile(r"[a-z0-9']+")
EMBEDDING_DIMENSIONS = 768


class EmbeddingProvider(ABC):
    """Common interface for demo and production embedding providers."""

    dimensions = EMBEDDING_DIMENSIONS
    model_name: str
    model_version: str

    @abstractmethod
    def embed(self, text: str, target_word: str | None = None) -> list[float]:
        raise NotImplementedError


def _normalize(vector: Iterable[float]) -> list[float]:
    values = list(vector)
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return values
    return [value / norm for value in values]


class HashingEmbeddingProvider(EmbeddingProvider):
    """Small deterministic embedding baseline for a credential-free demo.

    This is intentionally not presented as a replacement for EmbeddingGemma.
    It creates normalized 768-dimensional vectors from lexical and lightweight
    semantic features so the complete storage/retrieval flow can be tested
    before a model is downloaded.
    """

    model_name = "popsign/hash-context-768"
    model_version = "1"

    _concept_terms = {
        "ability": {"able", "ability", "can", "climb", "cook", "could", "do", "fly", "make", "possible", "run"},
        "container": {"bottle", "can", "container", "drink", "empty", "metal", "open", "opened", "recycle", "soda", "soup", "tin"},
        "approximate": {"about", "almost", "around", "estimate", "five", "nearly", "noon", "roughly", "ten", "time"},
        "topic": {"about", "book", "concerning", "discuss", "story", "talk", "talked", "think", "thinks", "topic"},
        "relationship": {"child", "dog", "family", "father", "friend", "friends", "her", "him", "love", "loves", "mother", "person"},
        "enjoyment": {"activity", "basketball", "delicious", "enjoy", "food", "game", "love", "loves", "paint", "pizza", "playing", "soup"},
    }

    def _add_feature(self, values: dict[int, float], feature: str, weight: float) -> None:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % self.dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        values[index] += sign * weight

    def embed(self, text: str, target_word: str | None = None) -> list[float]:
        tokens = TOKEN_RE.findall(text.casefold())
        target = target_word.casefold().strip() if target_word else None
        context_tokens = [token for token in tokens if token != target]
        values: dict[int, float] = defaultdict(float)

        for token in context_tokens:
            self._add_feature(values, f"token:{token}", 1.0)

        for left, right in zip(context_tokens, context_tokens[1:]):
            self._add_feature(values, f"bigram:{left}:{right}", 0.65)

        token_set = set(tokens)
        for concept, terms in self._concept_terms.items():
            hits = len(token_set & terms)
            if hits:
                self._add_feature(values, f"concept:{concept}", 1.75 * hits)

        normalized_text = " ".join(tokens)
        if target == "can":
            if re.search(r"\b(?:a|the|this|that|empty|metal|soda) can\b|\bcan of\b", normalized_text):
                self._add_feature(values, "syntax:can:container", 4.0)
                self._add_feature(values, "concept:container", 3.0)
            elif re.search(r"\bcan (?:cook|climb|do|fly|make|read|run|sing|swim|write)\b", normalized_text):
                self._add_feature(values, "syntax:can:ability", 4.0)
                self._add_feature(values, "concept:ability", 3.0)
        elif target == "about":
            if re.search(r"\babout (?:five|ten|[0-9]+|noon|an? hour|that time)\b", normalized_text):
                self._add_feature(values, "syntax:about:approximate", 4.0)
                self._add_feature(values, "concept:approximate", 3.0)
            elif re.search(r"\b(?:book|story|talk|talked|think|thinks)\b.*\babout\b|\babout (?:a|an|the|her|his|my|our)\b", normalized_text):
                self._add_feature(values, "syntax:about:topic", 4.0)
                self._add_feature(values, "concept:topic", 3.0)
        elif target == "love":
            if token_set & {"family", "mother", "father", "friend", "friends", "dog", "person", "child"}:
                self._add_feature(values, "syntax:love:relationship", 4.0)
                self._add_feature(values, "concept:relationship", 3.0)
            elif token_set & {"paint", "pizza", "basketball", "playing", "soup", "food", "activity", "game"}:
                self._add_feature(values, "syntax:love:enjoyment", 4.0)
                self._add_feature(values, "concept:enjoyment", 3.0)

        vector = [0.0] * self.dimensions
        for index, value in values.items():
            vector[index] = value
        return _normalize(vector)


class EmbeddingGemmaProvider(EmbeddingProvider):
    """Optional production-oriented provider backed by EmbeddingGemma."""

    model_name = "google/embeddinggemma-300M"
    model_version = "sentence-transformers-v1"

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "EmbeddingGemma support is not installed. Run `uv sync --extra ml`."
            ) from exc

        token = os.getenv("GEMMA_TOKEN") or os.getenv("HF_TOKEN")
        self._model = SentenceTransformer(self.model_name, token=token, device="cpu")

    def embed(self, text: str, target_word: str | None = None) -> list[float]:
        prompt = text.strip()
        if target_word:
            prompt = f'Meaning of "{target_word}" in this sentence: {prompt}'
        vector = self._model.encode(prompt, normalize_embeddings=True)
        values = [float(value) for value in vector]
        if len(values) != self.dimensions:
            raise ValueError(
                f"Expected {self.dimensions} embedding dimensions, received {len(values)}."
            )
        return values


def build_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    provider_name = (name or os.getenv("POPSIGN_EMBEDDING_PROVIDER", "hashing")).casefold()
    if provider_name in {"hash", "hashing", "demo"}:
        return HashingEmbeddingProvider()
    if provider_name in {"gemma", "embeddinggemma"}:
        return EmbeddingGemmaProvider()
    raise ValueError(f"Unknown embedding provider: {provider_name}")


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = list(left)
    right_values = list(right)
    if len(left_values) != len(right_values):
        raise ValueError("Embedding dimensions do not match.")
    return sum(a * b for a, b in zip(left_values, right_values))
