from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Iterable, Mapping, Sequence

from src.embeddings import EmbeddingProvider


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    dataset_name: str
    split: str
    word: str
    label_type: str
    expected_video_key: str | None
    query_embedding: tuple[float, ...]
    phrase: str | None = None
    expected_sense: str | None = None
    exclude_word_phrase_id: str | None = None


@dataclass(frozen=True)
class ScoredCase:
    case_id: str
    dataset_name: str
    split: str
    word: str
    label_type: str
    expected_video_key: str | None
    expected_sense: str | None
    recommended_video_key: str | None
    top_score: float
    runner_up_score: float
    margin: float

    def prediction(
        self,
        accept_threshold: float,
        margin_threshold: float,
    ) -> str | None:
        if (
            self.recommended_video_key is not None
            and self.top_score >= accept_threshold
            and self.margin >= margin_threshold
        ):
            return self.recommended_video_key
        return None


@dataclass(frozen=True)
class EvaluationMetrics:
    total: int
    positive_total: int
    ambiguous_total: int
    accepted: int
    correct: int
    correct_positive_accepts: int
    wrong_accepts: int
    ambiguous_rejections: int
    ranking_correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def accepted_precision(self) -> float:
        if not self.accepted:
            return 1.0
        return self.correct_positive_accepts / self.accepted

    @property
    def positive_coverage(self) -> float:
        if not self.positive_total:
            return 0.0
        return self.correct_positive_accepts / self.positive_total

    @property
    def ambiguous_rejection_rate(self) -> float:
        if not self.ambiguous_total:
            return 1.0
        return self.ambiguous_rejections / self.ambiguous_total

    @property
    def ambiguous_false_accept_rate(self) -> float:
        return 1.0 - self.ambiguous_rejection_rate

    @property
    def ranking_accuracy(self) -> float:
        if not self.positive_total:
            return 0.0
        return self.ranking_correct / self.positive_total

    @property
    def balanced_acceptance_score(self) -> float:
        return fmean((self.positive_coverage, self.ambiguous_rejection_rate))

    def to_dict(self) -> dict[str, int | float]:
        payload = asdict(self)
        payload.update(
            {
                "accuracy": self.accuracy,
                "accepted_precision": self.accepted_precision,
                "positive_coverage": self.positive_coverage,
                "ambiguous_rejection_rate": self.ambiguous_rejection_rate,
                "ambiguous_false_accept_rate": self.ambiguous_false_accept_rate,
                "ranking_accuracy": self.ranking_accuracy,
                "balanced_acceptance_score": self.balanced_acceptance_score,
            }
        )
        return payload


@dataclass(frozen=True)
class ThresholdCandidate:
    top_k_contexts: int
    accept_threshold: float
    margin_threshold: float
    metrics: EvaluationMetrics
    satisfies_safety_target: bool

    def to_dict(self) -> dict:
        return {
            "top_k_contexts": self.top_k_contexts,
            "accept_threshold": self.accept_threshold,
            "margin_threshold": self.margin_threshold,
            "satisfies_safety_target": self.satisfies_safety_target,
            "metrics": self.metrics.to_dict(),
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def _is_true(value: str) -> bool:
    return value.casefold() == "true"


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions do not match.")
    return sum(a * b for a, b in zip(left, right, strict=True))


def _split_ids(ids: Iterable[str]) -> dict[str, str]:
    """Create a deterministic roughly 2/3 calibration, 1/3 holdout split."""

    ordered = sorted(ids, key=lambda value: hashlib.sha256(value.encode()).digest())
    return {
        value: ("holdout" if index % 3 == 0 else "calibration")
        for index, value in enumerate(ordered)
    }


class ProductionEvidenceIndex:
    """Private production evidence loaded from the Phase 2 and 3 CSV exports.

    Only vectors needed for multi-variant evaluation words are materialized. Raw
    workbook phrases and canonical video keys never need to enter Git.
    """

    def __init__(
        self,
        *,
        word_variants: Mapping[str, tuple[str, ...]],
        video_key_by_variant: Mapping[str, str],
        evidence_ids_by_variant: Mapping[str, tuple[str, ...]],
        shared_ids_by_word: Mapping[str, tuple[str, ...]],
        phrase_by_word_phrase_id: Mapping[str, str],
        vectors: Mapping[str, tuple[float, ...]],
    ) -> None:
        self.word_variants = dict(word_variants)
        self.video_key_by_variant = dict(video_key_by_variant)
        self.evidence_ids_by_variant = dict(evidence_ids_by_variant)
        self.shared_ids_by_word = dict(shared_ids_by_word)
        self.phrase_by_word_phrase_id = dict(phrase_by_word_phrase_id)
        self.vectors = dict(vectors)

    @classmethod
    def from_exports(
        cls,
        dashboard_directory: Path,
        embedding_directory: Path,
    ) -> "ProductionEvidenceIndex":
        dashboard_directory = dashboard_directory.resolve()
        embedding_directory = embedding_directory.resolve()

        words = {
            row["id"]: row["word_key"]
            for row in _read_csv(dashboard_directory / "popsign_words.csv")
        }
        variants = {
            row["id"]: row
            for row in _read_csv(
                dashboard_directory / "popsign_sign_variants.csv"
            )
        }

        active_variants_by_word_id: dict[str, list[str]] = defaultdict(list)
        eligible_variants: set[str] = set()
        for variant_id, row in variants.items():
            if _is_true(row["is_active"]):
                active_variants_by_word_id[row["word_id"]].append(variant_id)
            if _is_true(row["is_active"]) and _is_true(row["matching_eligible"]):
                eligible_variants.add(variant_id)

        eligible_ids_by_variant: dict[str, set[str]] = defaultdict(set)
        shared_ids_by_word_id: dict[str, set[str]] = defaultdict(set)
        for row in _read_csv(
            dashboard_directory / "popsign_variant_contexts.csv"
        ):
            variant = variants[row["variant_id"]]
            if _is_true(row["matching_eligible"]):
                eligible_ids_by_variant[row["variant_id"]].add(
                    row["word_phrase_id"]
                )
            if (
                _is_true(row["shared_across_active_variants"])
                and _is_true(variant["is_active"])
            ):
                shared_ids_by_word_id[variant["word_id"]].add(
                    row["word_phrase_id"]
                )

        ready_word_ids = {
            word_id
            for word_id, variant_ids in active_variants_by_word_id.items()
            if len(variant_ids) > 1
            and all(variant_id in eligible_variants for variant_id in variant_ids)
            and all(eligible_ids_by_variant[variant_id] for variant_id in variant_ids)
        }
        word_variants = {
            words[word_id]: tuple(sorted(active_variants_by_word_id[word_id]))
            for word_id in ready_word_ids
        }
        relevant_variants = {
            variant_id for values in word_variants.values() for variant_id in values
        }
        relevant_word_phrase_ids = {
            word_phrase_id
            for variant_id in relevant_variants
            for word_phrase_id in eligible_ids_by_variant[variant_id]
        }
        relevant_word_phrase_ids.update(
            word_phrase_id
            for word_id in ready_word_ids
            for word_phrase_id in shared_ids_by_word_id[word_id]
        )

        word_phrase_to_phrase = {
            row["id"]: row["phrase_id"]
            for row in _read_csv(
                dashboard_directory / "popsign_word_phrases.csv"
            )
            if row["id"] in relevant_word_phrase_ids
        }
        relevant_phrase_ids = set(word_phrase_to_phrase.values())
        phrases = {
            row["id"]: row["context_text"]
            for row in _read_csv(dashboard_directory / "popsign_phrases.csv")
            if row["id"] in relevant_phrase_ids
        }
        phrase_by_word_phrase_id = {
            word_phrase_id: phrases[phrase_id]
            for word_phrase_id, phrase_id in word_phrase_to_phrase.items()
        }

        vectors: dict[str, tuple[float, ...]] = {}
        for path in sorted(embedding_directory.glob("popsign_phrase_embeddings_*.csv")):
            with path.open(newline="", encoding="utf-8") as source:
                for row in csv.DictReader(source):
                    word_phrase_id = row["word_phrase_id"]
                    if word_phrase_id in relevant_word_phrase_ids:
                        vector = tuple(float(value) for value in json.loads(row["embedding"]))
                        if len(vector) != 768 or not all(math.isfinite(v) for v in vector):
                            raise ValueError(
                                f"Invalid embedding for {word_phrase_id} in {path.name}."
                            )
                        vectors[word_phrase_id] = vector

        missing = relevant_word_phrase_ids - vectors.keys()
        if missing:
            raise ValueError(f"Missing {len(missing)} production embeddings.")

        return cls(
            word_variants=word_variants,
            video_key_by_variant={
                variant_id: variants[variant_id]["video_key"]
                for variant_id in relevant_variants
            },
            evidence_ids_by_variant={
                variant_id: tuple(sorted(eligible_ids_by_variant[variant_id]))
                for variant_id in relevant_variants
            },
            shared_ids_by_word={
                words[word_id]: tuple(sorted(shared_ids_by_word_id[word_id]))
                for word_id in ready_word_ids
            },
            phrase_by_word_phrase_id=phrase_by_word_phrase_id,
            vectors=vectors,
        )

    def score(
        self,
        word: str,
        query_embedding: Sequence[float],
        *,
        top_k_contexts: int,
        exclude_word_phrase_id: str | None = None,
    ) -> tuple[str | None, float, float]:
        if top_k_contexts < 1:
            raise ValueError("top_k_contexts must be positive.")

        candidates: list[tuple[str, float]] = []
        for variant_id in self.word_variants.get(word.casefold(), ()):
            similarities = sorted(
                (
                    _dot(query_embedding, self.vectors[word_phrase_id])
                    for word_phrase_id in self.evidence_ids_by_variant[variant_id]
                    if word_phrase_id != exclude_word_phrase_id
                ),
                reverse=True,
            )
            if not similarities:
                continue
            strongest = similarities[:top_k_contexts]
            candidates.append(
                (self.video_key_by_variant[variant_id], fmean(strongest))
            )

        candidates.sort(key=lambda item: item[1], reverse=True)
        if not candidates:
            return None, 0.0, 0.0
        top_video_key, top_score = candidates[0]
        runner_up_score = candidates[1][1] if len(candidates) > 1 else 0.0
        return top_video_key, top_score, runner_up_score

    def source_cases(self) -> list[EvaluationCase]:
        cases: list[EvaluationCase] = []
        for word in sorted(self.word_variants):
            for variant_id in self.word_variants[word]:
                word_phrase_ids = self.evidence_ids_by_variant[variant_id]
                if len(word_phrase_ids) < 2:
                    continue
                splits = _split_ids(word_phrase_ids)
                for word_phrase_id in word_phrase_ids:
                    cases.append(
                        EvaluationCase(
                            case_id=f"source-positive:{word}:{word_phrase_id}",
                            dataset_name="source_leave_one_out",
                            split=splits[word_phrase_id],
                            word=word,
                            label_type="positive",
                            expected_video_key=self.video_key_by_variant[variant_id],
                            query_embedding=self.vectors[word_phrase_id],
                            phrase=self.phrase_by_word_phrase_id[word_phrase_id],
                            exclude_word_phrase_id=word_phrase_id,
                        )
                    )

            shared_ids = self.shared_ids_by_word.get(word, ())
            splits = _split_ids(shared_ids)
            for word_phrase_id in shared_ids:
                cases.append(
                    EvaluationCase(
                        case_id=f"source-ambiguous:{word}:{word_phrase_id}",
                        dataset_name="source_shared_ambiguous",
                        split=splits[word_phrase_id],
                        word=word,
                        label_type="ambiguous",
                        expected_video_key=None,
                        query_embedding=self.vectors[word_phrase_id],
                        phrase=self.phrase_by_word_phrase_id[word_phrase_id],
                    )
                )
        return cases


def load_candidate_cases(
    cases_path: Path,
    sense_mapping_path: Path,
    provider: EmbeddingProvider,
    *,
    cached_embeddings: Mapping[str, Sequence[float]] | None = None,
) -> tuple[list[EvaluationCase], dict[str, list[float]]]:
    cases_payload = json.loads(cases_path.read_text(encoding="utf-8"))
    mapping_payload = json.loads(sense_mapping_path.read_text(encoding="utf-8"))
    mapping = {
        (row["word"].casefold(), row["sense_key"]): row["video_key"]
        for row in mapping_payload["mappings"]
    }
    cached = {key: list(value) for key, value in (cached_embeddings or {}).items()}
    rows = cases_payload["cases"]
    missing_rows = [row for row in rows if row["id"] not in cached]
    if missing_rows:
        vectors = provider.embed_many(
            (row["phrase"], row["word"]) for row in missing_rows
        )
        for row, vector in zip(missing_rows, vectors, strict=True):
            cached[row["id"]] = vector

    cases: list[EvaluationCase] = []
    for row in rows:
        word = row["word"].casefold()
        expected_sense = row.get("expected_sense")
        if expected_sense is None:
            expected_video_key = None
        else:
            try:
                expected_video_key = mapping[(word, expected_sense)]
            except KeyError as exc:
                raise ValueError(
                    f"No private sense mapping for {word}/{expected_sense}."
                ) from exc
        vector = tuple(float(value) for value in cached[row["id"]])
        if len(vector) != provider.dimensions:
            raise ValueError(f"Case {row['id']} has the wrong embedding dimensions.")
        cases.append(
            EvaluationCase(
                case_id=row["id"],
                dataset_name=cases_payload["dataset_name"],
                split=row["split"],
                word=word,
                label_type=row["label_type"],
                expected_video_key=expected_video_key,
                query_embedding=vector,
                phrase=row["phrase"],
                expected_sense=expected_sense,
            )
        )
    return cases, cached


def score_cases(
    index: ProductionEvidenceIndex,
    cases: Iterable[EvaluationCase],
    *,
    top_k_contexts: int,
) -> list[ScoredCase]:
    scored: list[ScoredCase] = []
    for case in cases:
        video_key, top_score, runner_up_score = index.score(
            case.word,
            case.query_embedding,
            top_k_contexts=top_k_contexts,
            exclude_word_phrase_id=case.exclude_word_phrase_id,
        )
        scored.append(
            ScoredCase(
                case_id=case.case_id,
                dataset_name=case.dataset_name,
                split=case.split,
                word=case.word,
                label_type=case.label_type,
                expected_video_key=case.expected_video_key,
                expected_sense=case.expected_sense,
                recommended_video_key=video_key,
                top_score=top_score,
                runner_up_score=runner_up_score,
                margin=top_score - runner_up_score,
            )
        )
    return scored


def evaluate(
    scored_cases: Iterable[ScoredCase],
    accept_threshold: float,
    margin_threshold: float,
) -> EvaluationMetrics:
    cases = list(scored_cases)
    positive_total = sum(case.expected_video_key is not None for case in cases)
    ambiguous_total = len(cases) - positive_total
    accepted = correct = correct_positive_accepts = wrong_accepts = 0
    ambiguous_rejections = ranking_correct = 0

    for case in cases:
        prediction = case.prediction(accept_threshold, margin_threshold)
        is_positive = case.expected_video_key is not None
        is_accepted = prediction is not None
        is_correct = prediction == case.expected_video_key
        accepted += int(is_accepted)
        correct += int(is_correct)
        correct_positive_accepts += int(is_positive and is_correct and is_accepted)
        wrong_accepts += int(is_accepted and not is_correct)
        ambiguous_rejections += int(not is_positive and not is_accepted)
        ranking_correct += int(
            is_positive and case.recommended_video_key == case.expected_video_key
        )

    return EvaluationMetrics(
        total=len(cases),
        positive_total=positive_total,
        ambiguous_total=ambiguous_total,
        accepted=accepted,
        correct=correct,
        correct_positive_accepts=correct_positive_accepts,
        wrong_accepts=wrong_accepts,
        ambiguous_rejections=ambiguous_rejections,
        ranking_correct=ranking_correct,
    )


def grid_search(
    scored_by_top_k: Mapping[int, Sequence[ScoredCase]],
    *,
    split: str = "calibration",
    minimum_precision: float = 0.95,
    minimum_ambiguous_rejection: float = 0.90,
) -> list[ThresholdCandidate]:
    candidates: list[ThresholdCandidate] = []
    for top_k, scored_cases_for_k in scored_by_top_k.items():
        selected_cases = [case for case in scored_cases_for_k if case.split == split]
        for accept_step in range(35, 96):
            accept_threshold = accept_step / 100
            for margin_step in range(0, 41):
                margin_threshold = margin_step / 100
                metrics = evaluate(
                    selected_cases,
                    accept_threshold,
                    margin_threshold,
                )
                satisfies = (
                    metrics.accepted_precision >= minimum_precision
                    and metrics.ambiguous_rejection_rate
                    >= minimum_ambiguous_rejection
                )
                candidates.append(
                    ThresholdCandidate(
                        top_k_contexts=top_k,
                        accept_threshold=accept_threshold,
                        margin_threshold=margin_threshold,
                        metrics=metrics,
                        satisfies_safety_target=satisfies,
                    )
                )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.satisfies_safety_target,
            candidate.metrics.balanced_acceptance_score,
            candidate.metrics.accepted_precision,
            candidate.metrics.accuracy,
            candidate.metrics.positive_coverage,
            -candidate.accept_threshold,
            -candidate.margin_threshold,
            -candidate.top_k_contexts,
        ),
        reverse=True,
    )


def metrics_by_group(
    scored_cases: Iterable[ScoredCase],
    accept_threshold: float,
    margin_threshold: float,
    *,
    group_field: str,
) -> dict[str, dict[str, int | float]]:
    groups: dict[str, list[ScoredCase]] = defaultdict(list)
    for case in scored_cases:
        groups[str(getattr(case, group_field))].append(case)
    return {
        group: evaluate(cases, accept_threshold, margin_threshold).to_dict()
        for group, cases in sorted(groups.items())
    }
