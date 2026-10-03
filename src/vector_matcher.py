from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Protocol

from src.embeddings import EmbeddingProvider, cosine_similarity


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "pilot_catalog.json"
CONFIG_PATH = ROOT / "data" / "matching_config.json"


@dataclass(frozen=True)
class ContextEvidence:
    context_id: str
    context_text: str
    word: str
    video_key: str
    sense_label: str
    definition: str
    similarity: float
    human_approved: bool


@dataclass(frozen=True)
class CandidateScore:
    video_key: str
    sense_label: str
    definition: str
    score: float
    evidence: tuple[ContextEvidence, ...]
    human_approved: bool


@dataclass(frozen=True)
class VectorMatchResult:
    phrase: str
    target_word: str
    accepted: bool
    decision: str
    selected_video_key: str | None
    selected_sense: str | None
    recommended_video_key: str | None
    recommended_sense: str | None
    top_score: float
    runner_up_score: float
    margin: float
    accept_threshold: float
    margin_threshold: float
    model_name: str
    model_version: str
    candidates: tuple[CandidateScore, ...]
    review_notice: str

    def to_dict(self) -> dict:
        return asdict(self)


class EvidenceSource(Protocol):
    review_notice: str

    def search(
        self,
        target_word: str,
        query_embedding: list[float],
        provider: EmbeddingProvider,
    ) -> list[ContextEvidence]: ...


class LocalEvidenceSource:
    def __init__(self, path: Path = CATALOG_PATH) -> None:
        with path.open(encoding="utf-8") as file:
            payload = json.load(file)
        self.senses = payload["senses"]
        self.review_notice = payload["review_notice"]

    def words(self) -> list[str]:
        return sorted({sense["word"] for sense in self.senses})

    def search(
        self,
        target_word: str,
        query_embedding: list[float],
        provider: EmbeddingProvider,
    ) -> list[ContextEvidence]:
        evidence: list[ContextEvidence] = []
        key = target_word.casefold().strip()
        for sense in self.senses:
            if sense["word"].casefold() != key:
                continue
            for context in sense["contexts"]:
                context_embedding = provider.embed(context["text"], target_word)
                evidence.append(
                    ContextEvidence(
                        context_id=context["id"],
                        context_text=context["text"],
                        word=sense["word"],
                        video_key=sense["video_key"],
                        sense_label=sense["sense_label"],
                        definition=sense["definition"],
                        similarity=cosine_similarity(query_embedding, context_embedding),
                        human_approved=bool(sense.get("human_approved", False)),
                    )
                )
        return evidence


class SupabaseEvidenceSource:
    review_notice = (
        "Database sense labels remain provisional until the PopSign ASL team approves them."
    )

    def __init__(self, url: str | None = None, secret_key: str | None = None) -> None:
        from supabase import create_client

        resolved_url = url or os.getenv("SUPABASE_URL")
        resolved_key = secret_key or os.getenv("SUPABASE_SECRET_KEY")
        if not resolved_url or not resolved_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SECRET_KEY are required for the Supabase backend."
            )
        self.client = create_client(resolved_url, resolved_key)

    def search(
        self,
        target_word: str,
        query_embedding: list[float],
        provider: EmbeddingProvider,
    ) -> list[ContextEvidence]:
        response = self.client.rpc(
            "match_context_phrases",
            {
                "p_target_word": target_word.casefold().strip(),
                "p_query_embedding": query_embedding,
                "p_query_model_name": provider.model_name,
                "p_query_model_version": provider.model_version,
                "p_match_limit": 24,
            },
        ).execute()

        return [
            ContextEvidence(
                context_id=row["context_id"],
                context_text=row["context_text"],
                word=row["word"],
                video_key=row["video_key"],
                sense_label=row["sense_label"],
                definition=row["definition"],
                similarity=float(row["similarity"]),
                human_approved=bool(row["human_approved"]),
            )
            for row in (response.data or [])
        ]


def load_matching_config(path: Path = CONFIG_PATH) -> dict:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


class VectorMatcher:
    def __init__(
        self,
        provider: EmbeddingProvider,
        source: EvidenceSource,
        config: dict | None = None,
    ) -> None:
        self.provider = provider
        self.source = source
        self.config = config or load_matching_config()

    def _thresholds(self, target_word: str) -> tuple[float, float, int]:
        settings = dict(self.config["global"])
        settings.update(self.config.get("per_word", {}).get(target_word.casefold(), {}))
        accept = float(os.getenv("POPSIGN_ACCEPT_THRESHOLD", settings["accept_threshold"]))
        margin = float(os.getenv("POPSIGN_MARGIN_THRESHOLD", settings["margin_threshold"]))
        return accept, margin, int(settings["top_k_contexts"])

    def match(self, phrase: str, target_word: str) -> VectorMatchResult:
        cleaned_phrase = phrase.strip()
        cleaned_word = target_word.casefold().strip()
        if not cleaned_phrase or not cleaned_word:
            raise ValueError("Both phrase and target_word are required.")

        query_embedding = self.provider.embed(cleaned_phrase, cleaned_word)
        evidence = self.source.search(cleaned_word, query_embedding, self.provider)
        accept_threshold, margin_threshold, top_k = self._thresholds(cleaned_word)

        by_video: dict[str, list[ContextEvidence]] = defaultdict(list)
        for item in evidence:
            by_video[item.video_key].append(item)

        candidates: list[CandidateScore] = []
        for video_key, items in by_video.items():
            ranked = sorted(items, key=lambda item: item.similarity, reverse=True)
            strongest = tuple(ranked[:top_k])
            candidates.append(
                CandidateScore(
                    video_key=video_key,
                    sense_label=strongest[0].sense_label,
                    definition=strongest[0].definition,
                    score=fmean(item.similarity for item in strongest),
                    evidence=strongest,
                    human_approved=all(item.human_approved for item in strongest),
                )
            )

        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        top = candidates[0] if candidates else None
        runner_up = candidates[1] if len(candidates) > 1 else None
        top_score = top.score if top else 0.0
        runner_up_score = runner_up.score if runner_up else 0.0
        margin = top_score - runner_up_score
        accepted = bool(
            top
            and top_score >= accept_threshold
            and (runner_up is None or margin >= margin_threshold)
        )

        return VectorMatchResult(
            phrase=cleaned_phrase,
            target_word=cleaned_word,
            accepted=accepted,
            decision="accepted" if accepted else ("needs_review" if top else "no_candidates"),
            selected_video_key=top.video_key if accepted and top else None,
            selected_sense=top.sense_label if accepted and top else None,
            recommended_video_key=top.video_key if top else None,
            recommended_sense=top.sense_label if top else None,
            top_score=top_score,
            runner_up_score=runner_up_score,
            margin=margin,
            accept_threshold=accept_threshold,
            margin_threshold=margin_threshold,
            model_name=self.provider.model_name,
            model_version=self.provider.model_version,
            candidates=tuple(candidates),
            review_notice=self.source.review_notice,
        )
