from __future__ import annotations

from src.threshold_evaluation import (
    EvaluationCase,
    ScoredCase,
    ThresholdCandidate,
    evaluate,
    grid_search,
)


def _scored(
    case_id: str,
    expected: str | None,
    recommended: str,
    top: float,
    margin: float,
    *,
    split: str = "calibration",
) -> ScoredCase:
    return ScoredCase(
        case_id=case_id,
        dataset_name="test",
        split=split,
        word="can",
        label_type="positive" if expected else "ambiguous",
        expected_video_key=expected,
        expected_sense=None,
        recommended_video_key=recommended,
        top_score=top,
        runner_up_score=top - margin,
        margin=margin,
    )


def test_scored_case_requires_both_thresholds():
    case = _scored("one", "ability", "ability", 0.80, 0.09)

    assert case.prediction(0.75, 0.08) == "ability"
    assert case.prediction(0.81, 0.08) is None
    assert case.prediction(0.75, 0.10) is None


def test_metrics_count_correct_accepts_and_ambiguous_rejections():
    cases = [
        _scored("positive-correct", "ability", "ability", 0.80, 0.20),
        _scored("positive-wrong", "container", "ability", 0.78, 0.18),
        _scored("ambiguous-reject", None, "ability", 0.70, 0.02),
        _scored("ambiguous-accept", None, "container", 0.90, 0.30),
    ]

    metrics = evaluate(cases, accept_threshold=0.75, margin_threshold=0.10)

    assert metrics.total == 4
    assert metrics.accepted == 3
    assert metrics.correct == 2
    assert metrics.correct_positive_accepts == 1
    assert metrics.wrong_accepts == 2
    assert metrics.ambiguous_rejections == 1
    assert metrics.accepted_precision == 1 / 3
    assert metrics.positive_coverage == 0.5
    assert metrics.ambiguous_rejection_rate == 0.5


def test_grid_search_prefers_a_safe_candidate_with_useful_coverage():
    cases = [
        _scored("positive-1", "ability", "ability", 0.82, 0.22),
        _scored("positive-2", "container", "container", 0.79, 0.18),
        _scored("ambiguous-1", None, "ability", 0.72, 0.03),
        _scored("ambiguous-2", None, "container", 0.70, 0.02),
    ]

    best: ThresholdCandidate = grid_search({1: cases})[0]

    assert best.satisfies_safety_target
    assert best.metrics.accepted_precision == 1.0
    assert best.metrics.positive_coverage == 1.0
    assert best.metrics.ambiguous_rejection_rate == 1.0


def test_evaluation_case_supports_private_source_holdout_metadata():
    case = EvaluationCase(
        case_id="source-case",
        dataset_name="source_leave_one_out",
        split="holdout",
        word="can",
        label_type="positive",
        expected_video_key="ability",
        query_embedding=(1.0, 0.0),
        phrase="A child can read.",
        exclude_word_phrase_id="word-phrase-id",
    )

    assert case.exclude_word_phrase_id == "word-phrase-id"
    assert case.split == "holdout"
