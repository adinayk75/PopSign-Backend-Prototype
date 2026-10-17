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
    provider_kind: str
    prompt_template: str

    @abstractmethod
    def embed(self, text: str, target_word: str | None = None) -> list[float]:
        raise NotImplementedError

    def embed_many(
        self,
        items: Iterable[tuple[str, str | None]],
    ) -> list[list[float]]:
        """Embed several inputs with a scalar fallback for lightweight providers."""

        return [self.embed(text, target_word) for text, target_word in items]


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
    provider_kind = "hashing_demo"
    prompt_template = "hashing-demo-v1(target_word={target_word}, context={context_text})"

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


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Version-pinned, batched sentence-transformers embedding provider."""

    provider_kind = "sentence_transformers"
    prompt_template = 'Meaning of "{target_word}" in this sentence: {context_text}'
    model_name: str
    revision_environment_variable: str
    default_revision: str | None = None

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Semantic embedding support is not installed. "
                "Run `uv sync --extra ml`."
            ) from exc

        token = os.getenv("GEMMA_TOKEN") or os.getenv("HF_TOKEN")
        revision = (
            os.getenv(self.revision_environment_variable)
            or os.getenv("POPSIGN_EMBEDDING_MODEL_REVISION")
            or self.default_revision
        )
        if not revision:
            raise RuntimeError(
                f"Set {self.revision_environment_variable} to an immutable "
                f"Hugging Face commit SHA for {self.model_name}."
            )

        self.model_version = f"hf-{revision}"
        model_options = {
            "token": token,
            "device": "cpu",
            "revision": revision,
        }
        self._model = SentenceTransformer(self.model_name, **model_options)

        dimension_reader = getattr(self._model, "get_embedding_dimension", None)
        if dimension_reader is None:
            dimension_reader = self._model.get_sentence_embedding_dimension
        actual_dimensions = int(dimension_reader())
        if actual_dimensions != self.dimensions:
            raise ValueError(
                f"Expected {self.dimensions} embedding dimensions, "
                f"received {actual_dimensions}."
            )

    def _prompt(self, text: str, target_word: str | None) -> str:
        normalized = text.strip()
        if not target_word:
            return normalized
        return self.prompt_template.format(
            target_word=target_word.strip(),
            context_text=normalized,
        )

    def embed(self, text: str, target_word: str | None = None) -> list[float]:
        return self.embed_many([(text, target_word)])[0]

    def embed_many(
        self,
        items: Iterable[tuple[str, str | None]],
    ) -> list[list[float]]:
        materialized = list(items)
        if not materialized:
            return []

        prompts = [self._prompt(text, target_word) for text, target_word in materialized]
        batch_size = int(os.getenv("POPSIGN_MODEL_BATCH_SIZE", "32"))
        vectors = self._model.encode(
            prompts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        rows = [[float(value) for value in vector] for vector in vectors]
        if len(rows) != len(materialized):
            raise ValueError(
                f"Expected {len(materialized)} embeddings, received {len(rows)}."
            )
        for values in rows:
            if len(values) != self.dimensions:
                raise ValueError(
                    f"Expected {self.dimensions} embedding dimensions, "
                    f"received {len(values)}."
                )
        return rows


class MpnetEmbeddingProvider(SentenceTransformerEmbeddingProvider):
    """Credential-free Apache-2.0 semantic model for the production candidate run."""

    model_name = "sentence-transformers/all-mpnet-base-v2"
    revision_environment_variable = "POPSIGN_MPNET_MODEL_REVISION"
    default_revision = "e8c3b32edf5434bc2275fc9bab85f82640a19130"


class EmbeddingGemmaProvider(SentenceTransformerEmbeddingProvider):
    """Optional gated provider backed by Google's EmbeddingGemma model."""

    model_name = "google/embeddinggemma-300M"
    revision_environment_variable = "POPSIGN_EMBEDDING_MODEL_REVISION"
    default_revision = None


def build_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    provider_name = (name or os.getenv("POPSIGN_EMBEDDING_PROVIDER", "hashing")).casefold()
    if provider_name in {"hash", "hashing", "demo"}:
        return HashingEmbeddingProvider()
    if provider_name in {"mpnet", "all-mpnet-base-v2"}:
        return MpnetEmbeddingProvider()
    if provider_name in {"gemma", "embeddinggemma"}:
        return EmbeddingGemmaProvider()
    raise ValueError(f"Unknown embedding provider: {provider_name}")


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = list(left)
    right_values = list(right)
    if len(left_values) != len(right_values):
        raise ValueError("Embedding dimensions do not match.")
    return sum(a * b for a, b in zip(left_values, right_values))
