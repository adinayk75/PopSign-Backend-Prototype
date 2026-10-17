from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.context_bank import stable_uuid
from src.embeddings import MpnetEmbeddingProvider
from src.threshold_evaluation import (
    ProductionEvidenceIndex,
    evaluate,
    grid_search,
    load_candidate_cases,
    metrics_by_group,
    score_cases,
)


DEFAULT_CASES = ROOT / "data" / "phase4_candidate_cases.json"
DEFAULT_SENSE_MAPPING = ROOT / ".popsign-state" / "phase4" / "candidate_sense_mapping.json"
DEFAULT_CACHE = ROOT / ".popsign-state" / "phase4" / "query_embedding_checkpoint.json"
DEFAULT_PRIVATE_OUTPUT = ROOT / ".popsign-state" / "phase4" / "full_evaluation.json"
DEFAULT_CASE_REVIEW = ROOT / ".popsign-state" / "phase4" / "case_label_review.csv"
DEFAULT_MAPPING_REVIEW = ROOT / ".popsign-state" / "phase4" / "sense_mapping_review.csv"
DEFAULT_PUBLIC_OUTPUT = ROOT / "data" / "phase4_threshold_evaluation.json"
DEFAULT_CONFIG_OUTPUT = ROOT / "data" / "phase4_candidate_matching_config.json"
DEFAULT_CHART_OUTPUT = ROOT / "data" / "phase4_threshold_tradeoff.svg"


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {}

    def value_at(percent: float) -> float:
        index = round((len(ordered) - 1) * percent)
        return ordered[index]

    return {
        "minimum": ordered[0],
        "p10": value_at(0.10),
        "p25": value_at(0.25),
        "median": value_at(0.50),
        "p75": value_at(0.75),
        "p90": value_at(0.90),
        "maximum": ordered[-1],
    }


def _discover_export(prefix: str) -> Path:
    candidates: list[Path] = []
    for path in (ROOT / ".popsign-state").glob(f"{prefix}*"):
        manifest = path / "manifest.json"
        if not manifest.is_file():
            continue
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("status") == "completed":
            candidates.append(path)
    if not candidates:
        raise FileNotFoundError(f"No completed {prefix} export was found.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_cache(
    path: Path,
    *,
    model_name: str,
    model_version: str,
    cases_sha256: str,
) -> dict[str, list[float]]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    identity = (
        payload.get("model_name"),
        payload.get("model_version"),
        payload.get("cases_sha256"),
    )
    expected = (model_name, model_version, cases_sha256)
    if identity != expected:
        return {}
    return payload.get("embeddings", {})


def _write_case_review(path: Path, cases_payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        fieldnames = [
            "case_id",
            "split",
            "word",
            "phrase",
            "label_type",
            "proposed_sense",
            "reviewer_approved",
            "corrected_sense",
            "reviewer",
            "notes",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in cases_payload["cases"]:
            writer.writerow(
                {
                    "case_id": row["id"],
                    "split": row["split"],
                    "word": row["word"],
                    "phrase": row["phrase"],
                    "label_type": row["label_type"],
                    "proposed_sense": row.get("expected_sense") or "abstain",
                    "reviewer_approved": "",
                    "corrected_sense": "",
                    "reviewer": "",
                    "notes": "",
                }
            )


def _write_mapping_review(
    path: Path,
    mapping_payload: dict,
    dashboard_directory: Path,
    index: ProductionEvidenceIndex,
) -> None:
    with (dashboard_directory / "popsign_sign_variants.csv").open(
        newline="", encoding="utf-8"
    ) as source:
        variants = {row["video_key"]: row for row in csv.DictReader(source)}
    variant_by_video = {
        video_key: variant_id
        for variant_id, video_key in index.video_key_by_variant.items()
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        fieldnames = [
            "word",
            "sense_key",
            "candidate_video_key",
            "legacy_video_ref",
            "sample_source_contexts",
            "reviewer_approved",
            "corrected_video_key",
            "reviewer",
            "notes",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in mapping_payload["mappings"]:
            video_key = row["video_key"]
            variant_id = variant_by_video[video_key]
            sample_ids = index.evidence_ids_by_variant[variant_id][:3]
            writer.writerow(
                {
                    "word": row["word"],
                    "sense_key": row["sense_key"],
                    "candidate_video_key": video_key,
                    "legacy_video_ref": variants[video_key]["legacy_video_ref"],
                    "sample_source_contexts": " || ".join(
                        index.phrase_by_word_phrase_id[item] for item in sample_ids
                    ),
                    "reviewer_approved": "",
                    "corrected_video_key": "",
                    "reviewer": "",
                    "notes": "",
                }
            )


def _write_tradeoff_svg(path: Path, public_result: dict) -> None:
    width, height = 900, 480
    left, right, top, bottom = 80, 40, 70, 70
    plot_width = width - left - right
    plot_height = height - top - bottom
    sweep = public_result["margin_sweep"]

    def x(value: float) -> float:
        return left + (value / 0.25) * plot_width

    def y(value: float) -> float:
        return top + (1.0 - value) * plot_height

    series = (
        ("Accepted precision", "#2563eb", "accepted_precision"),
        ("Positive coverage", "#16a34a", "positive_coverage"),
        ("Ambiguous rejection", "#ea580c", "ambiguous_rejection_rate"),
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:system-ui,sans-serif;fill:#111827}.axis{stroke:#374151;stroke-width:1}.grid{stroke:#e5e7eb;stroke-width:1}.line{fill:none;stroke-width:3}</style>',
        '<text x="450" y="30" text-anchor="middle" font-size="20" font-weight="700">Holdout trade-off as runner-up margin increases</text>',
    ]
    for tick in range(0, 6):
        value = tick / 5
        y_value = y(value)
        parts.append(
            f'<line class="grid" x1="{left}" y1="{y_value:.1f}" x2="{width-right}" y2="{y_value:.1f}"/>'
        )
        parts.append(
            f'<text x="{left-12}" y="{y_value+5:.1f}" text-anchor="end" font-size="12">{value:.0%}</text>'
        )
    for tick in range(0, 6):
        value = tick * 0.05
        x_value = x(value)
        parts.append(
            f'<line class="grid" x1="{x_value:.1f}" y1="{top}" x2="{x_value:.1f}" y2="{height-bottom}"/>'
        )
        parts.append(
            f'<text x="{x_value:.1f}" y="{height-bottom+24}" text-anchor="middle" font-size="12">{value:.2f}</text>'
        )
    parts.extend(
        [
            f'<line class="axis" x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}"/>',
            f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}"/>',
            f'<text x="{left+plot_width/2:.1f}" y="{height-18}" text-anchor="middle" font-size="14">Runner-up margin threshold</text>',
            f'<text x="20" y="{top+plot_height/2:.1f}" text-anchor="middle" font-size="14" transform="rotate(-90 20 {top+plot_height/2:.1f})">Rate</text>',
        ]
    )
    for index, (label, color, metric) in enumerate(series):
        points = " ".join(
            f'{x(row["margin_threshold"]):.1f},{y(row["holdout"][metric]):.1f}'
            for row in sweep
        )
        parts.append(f'<polyline class="line" stroke="{color}" points="{points}"/>')
        legend_x = 205 + index * 230
        parts.append(
            f'<line x1="{legend_x}" y1="50" x2="{legend_x+28}" y2="50" stroke="{color}" stroke-width="4"/>'
        )
        parts.append(
            f'<text x="{legend_x+36}" y="55" font-size="13">{label}</text>'
        )
    candidate_margin = public_result["candidate_global_threshold"][
        "margin_threshold"
    ]
    candidate_x = x(candidate_margin)
    parts.append(
        f'<line x1="{candidate_x:.1f}" y1="{top}" x2="{candidate_x:.1f}" y2="{height-bottom}" stroke="#7c3aed" stroke-width="2" stroke-dasharray="7 5"/>'
    )
    parts.append(
        f'<text x="{candidate_x+6:.1f}" y="{top+18}" font-size="12" fill="#7c3aed">candidate {candidate_margin:.2f}</text>'
    )
    parts.append("</svg>\n")
    path.write_text("".join(parts), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the pinned Phase 3 MPNet vectors with source holdouts and "
            "LLM-generated candidate labels. Results remain inactive until review."
        )
    )
    parser.add_argument("--dashboard-directory", type=Path)
    parser.add_argument("--embedding-directory", type=Path)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--sense-mapping", type=Path, default=DEFAULT_SENSE_MAPPING)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--private-output", type=Path, default=DEFAULT_PRIVATE_OUTPUT)
    parser.add_argument("--public-output", type=Path, default=DEFAULT_PUBLIC_OUTPUT)
    parser.add_argument("--config-output", type=Path, default=DEFAULT_CONFIG_OUTPUT)
    parser.add_argument("--chart-output", type=Path, default=DEFAULT_CHART_OUTPUT)
    parser.add_argument("--case-review", type=Path, default=DEFAULT_CASE_REVIEW)
    parser.add_argument("--mapping-review", type=Path, default=DEFAULT_MAPPING_REVIEW)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dashboard_directory = (
        args.dashboard_directory or _discover_export("dashboard-import-")
    )
    embedding_directory = (
        args.embedding_directory or _discover_export("embedding-export-")
    )

    print("Loading the private Phase 2/3 exports...")
    index = ProductionEvidenceIndex.from_exports(
        dashboard_directory,
        embedding_directory,
    )
    source_cases = index.source_cases()
    print(
        f"Loaded {len(index.word_variants)} multi-variant words and "
        f"{len(source_cases)} source-derived cases."
    )

    provider = MpnetEmbeddingProvider()
    cases_sha256 = _sha256(args.cases)
    cache = _load_cache(
        args.cache,
        model_name=provider.model_name,
        model_version=provider.model_version,
        cases_sha256=cases_sha256,
    )
    print(f"Embedding checkpoint contains {len(cache)} candidate cases.")
    candidate_cases, cache = load_candidate_cases(
        args.cases,
        args.sense_mapping,
        provider,
        cached_embeddings=cache,
    )
    _atomic_json(
        args.cache,
        {
            "cases_sha256": cases_sha256,
            "model_name": provider.model_name,
            "model_version": provider.model_version,
            "embeddings": cache,
        },
    )
    print(f"Candidate query embeddings complete: {len(candidate_cases)} cases.")

    all_cases = [*source_cases, *candidate_cases]
    top_k_values = (1, 2, 3, 5)
    scored_by_top_k = {}
    for top_k in top_k_values:
        print(f"Scoring {len(all_cases)} cases with top_k={top_k}...")
        scored_by_top_k[top_k] = score_cases(
            index,
            all_cases,
            top_k_contexts=top_k,
        )

    ranked = grid_search(scored_by_top_k)
    best = ranked[0]
    scored = scored_by_top_k[best.top_k_contexts]
    calibration = [case for case in scored if case.split == "calibration"]
    holdout = [case for case in scored if case.split == "holdout"]
    holdout_metrics = evaluate(
        holdout,
        best.accept_threshold,
        best.margin_threshold,
    )

    llm_scored_by_top_k = {
        top_k: [
            case
            for case in top_k_cases
            if case.dataset_name == "popsign_phase4_llm_candidate"
        ]
        for top_k, top_k_cases in scored_by_top_k.items()
    }
    per_word_candidates = {}
    llm_words = sorted({case.word for case in candidate_cases})
    for word in llm_words:
        word_scored_by_top_k = {
            top_k: [case for case in cases if case.word == word]
            for top_k, cases in llm_scored_by_top_k.items()
        }
        word_candidate = grid_search(word_scored_by_top_k)[0]
        word_holdout = [
            case
            for case in word_scored_by_top_k[word_candidate.top_k_contexts]
            if case.split == "holdout"
        ]
        word_holdout_metrics = evaluate(
            word_holdout,
            word_candidate.accept_threshold,
            word_candidate.margin_threshold,
        )
        per_word_candidates[word] = {
            "accept_threshold": word_candidate.accept_threshold,
            "margin_threshold": word_candidate.margin_threshold,
            "top_k_contexts": word_candidate.top_k_contexts,
            "calibration_metrics": word_candidate.metrics.to_dict(),
            "holdout_metrics": word_holdout_metrics.to_dict(),
            "is_active": False,
            "recommendation": "do_not_activate_before_label_review",
        }

    model_payload = json.loads(
        (ROOT / "data" / "phase3_embedding_verification.json").read_text(
            encoding="utf-8"
        )
    )["embedding_model"]
    cases_payload = json.loads(args.cases.read_text(encoding="utf-8"))
    mapping_payload = json.loads(args.sense_mapping.read_text(encoding="utf-8"))
    generated_at = datetime.now(UTC).isoformat()
    evaluation_run_id = stable_uuid(
        "evaluation_run",
        model_payload["id"],
        cases_payload["dataset_name"],
        cases_payload["dataset_version"],
        cases_sha256,
        best.top_k_contexts,
        best.accept_threshold,
        best.margin_threshold,
    )
    threshold_id = stable_uuid(
        "matching_threshold",
        model_payload["id"],
        "global",
        evaluation_run_id,
    )

    case_counts = {
        "total": len(all_cases),
        "calibration": len(calibration),
        "holdout": len(holdout),
        "source_derived": len(source_cases),
        "llm_generated": len(candidate_cases),
        "positive": sum(case.expected_video_key is not None for case in all_cases),
        "ambiguous": sum(case.expected_video_key is None for case in all_cases),
        "multi_variant_words": len(index.word_variants),
        "human_reviewed": 0,
    }
    llm_holdout = [
        case
        for case in holdout
        if case.dataset_name == cases_payload["dataset_name"]
    ]
    llm_holdout_metrics = evaluate(
        llm_holdout,
        best.accept_threshold,
        best.margin_threshold,
    )
    activation_gates = {
        "overall_holdout_precision_at_least_95_percent": (
            holdout_metrics.accepted_precision >= 0.95
        ),
        "overall_holdout_ambiguous_rejection_at_least_90_percent": (
            holdout_metrics.ambiguous_rejection_rate >= 0.90
        ),
        "overall_holdout_positive_coverage_at_least_60_percent": (
            holdout_metrics.positive_coverage >= 0.60
        ),
        "llm_holdout_precision_at_least_95_percent": (
            llm_holdout_metrics.accepted_precision >= 0.95
        ),
        "llm_holdout_ambiguous_rejection_at_least_90_percent": (
            llm_holdout_metrics.ambiguous_rejection_rate >= 0.90
        ),
        "labels_human_reviewed": False,
    }
    margin_sweep = []
    for margin_step in range(0, 26):
        margin = margin_step / 100
        margin_sweep.append(
            {
                "margin_threshold": margin,
                "calibration": evaluate(
                    calibration,
                    best.accept_threshold,
                    margin,
                ).to_dict(),
                "holdout": evaluate(
                    holdout,
                    best.accept_threshold,
                    margin,
                ).to_dict(),
            }
        )
    score_distributions = {}
    for split_name, split_cases in (
        ("calibration", calibration),
        ("holdout", holdout),
    ):
        score_distributions[split_name] = {}
        for label_type in ("positive", "ambiguous"):
            selected = [
                case for case in split_cases if case.label_type == label_type
            ]
            score_distributions[split_name][label_type] = {
                "top_score": _percentiles([case.top_score for case in selected]),
                "margin": _percentiles([case.margin for case in selected]),
            }
    public_result = {
        "schema_version": "2026-10-17.1",
        "phase": "threshold_candidate_complete",
        "generated_at": generated_at,
        "embedding_model": model_payload,
        "evaluation_run_id": evaluation_run_id,
        "threshold_id": threshold_id,
        "datasets": {
            "source_holdout": {
                "label_source": "private workbook assignments",
                "label_status": "provisional_not_human_approved",
            },
            "llm_candidate": {
                "name": cases_payload["dataset_name"],
                "version": cases_payload["dataset_version"],
                "sha256": cases_sha256,
                "label_status": cases_payload["label_status"],
            },
        },
        "case_counts": case_counts,
        "selection_target": {
            "minimum_accepted_precision": 0.95,
            "minimum_ambiguous_rejection_rate": 0.90,
        },
        "candidate_global_threshold": {
            "accept_threshold": best.accept_threshold,
            "margin_threshold": best.margin_threshold,
            "top_k_contexts": best.top_k_contexts,
            "is_active": False,
            "satisfies_calibration_safety_target": best.satisfies_safety_target,
        },
        "calibration_metrics": best.metrics.to_dict(),
        "holdout_metrics": holdout_metrics.to_dict(),
        "holdout_metrics_by_dataset": metrics_by_group(
            holdout,
            best.accept_threshold,
            best.margin_threshold,
            group_field="dataset_name",
        ),
        "llm_holdout_metrics_by_word": metrics_by_group(
            [
                case
                for case in holdout
                if case.dataset_name == cases_payload["dataset_name"]
            ],
            best.accept_threshold,
            best.margin_threshold,
            group_field="word",
        ),
        "candidate_per_word_thresholds": per_word_candidates,
        "margin_sweep": margin_sweep,
        "score_distributions": score_distributions,
        "top_alternatives": [candidate.to_dict() for candidate in ranked[:10]],
        "per_word_override_status": (
            "not_recommended_until_labels_are_human_reviewed"
        ),
        "activation_status": "inactive_pending_asl_label_review",
        "activation_gates": activation_gates,
        "activation_recommended": all(activation_gates.values()),
    }
    _atomic_json(args.public_output, public_result)
    _write_tradeoff_svg(args.chart_output, public_result)
    _atomic_json(
        args.config_output,
        {
            "schema_version": "2026-10-17.1",
            "model_name": provider.model_name,
            "model_version": provider.model_version,
            "evaluation_run_id": evaluation_run_id,
            "global": {
                "accept_threshold": best.accept_threshold,
                "margin_threshold": best.margin_threshold,
                "top_k_contexts": best.top_k_contexts,
            },
            "per_word": {},
            "is_active": False,
            "activation_blocker": "ASL label review is incomplete.",
        },
    )

    case_by_id = {case.case_id: case for case in all_cases}
    _atomic_json(
        args.private_output,
        {
            **public_result,
            "private_warning": "Contains private source phrases and video keys; do not commit.",
            "cases": [
                {
                    **asdict(case),
                    "phrase": case_by_id[case.case_id].phrase,
                    "prediction": case.prediction(
                        best.accept_threshold,
                        best.margin_threshold,
                    ),
                }
                for case in scored
            ],
        },
    )
    _write_case_review(args.case_review, cases_payload)
    _write_mapping_review(
        args.mapping_review,
        mapping_payload,
        dashboard_directory,
        index,
    )

    print("\nCandidate global rule")
    print(f"  accept threshold: {best.accept_threshold:.2f}")
    print(f"  runner-up margin: {best.margin_threshold:.2f}")
    print(f"  top contexts:     {best.top_k_contexts}")
    print(f"  calibration:      {best.metrics.accuracy:.1%} accuracy")
    print(f"  holdout:          {holdout_metrics.accuracy:.1%} accuracy")
    print(f"  holdout precision:{holdout_metrics.accepted_precision:.1%}")
    print(f"  holdout coverage: {holdout_metrics.positive_coverage:.1%}")
    print(
        f"  ambiguous reject: {holdout_metrics.ambiguous_rejection_rate:.1%}"
    )
    print("\nThreshold remains inactive until the ASL label review is completed.")


if __name__ == "__main__":
    main()
