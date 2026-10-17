import json
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_candidate_cases_are_public_safe_and_stratified():
    payload = json.loads(
        (ROOT / "data" / "phase4_candidate_cases.json").read_text(encoding="utf-8")
    )
    cases = payload["cases"]

    assert len(cases) == 78
    assert len({case["id"] for case in cases}) == 78
    assert sum(case["split"] == "calibration" for case in cases) == 54
    assert sum(case["split"] == "holdout" for case in cases) == 24
    assert sum(case["label_type"] == "positive" for case in cases) == 60
    assert sum(case["label_type"] == "ambiguous" for case in cases) == 18
    assert {case["word"] for case in cases} == {"about", "can", "love"}

    serialized = json.dumps(payload)
    assert "psv_" not in serialized
    assert "legacy_video_ref" not in serialized
    assert payload["label_status"] == "candidate_needs_asl_review"


def test_phase4_result_and_candidate_config_stay_inactive_and_consistent():
    result = json.loads(
        (ROOT / "data" / "phase4_threshold_evaluation.json").read_text(
            encoding="utf-8"
        )
    )
    config = json.loads(
        (ROOT / "data" / "phase4_candidate_matching_config.json").read_text(
            encoding="utf-8"
        )
    )
    candidate = result["candidate_global_threshold"]

    assert result["case_counts"] == {
        "ambiguous": 90,
        "calibration": 376,
        "holdout": 200,
        "human_reviewed": 0,
        "llm_generated": 78,
        "multi_variant_words": 15,
        "positive": 486,
        "source_derived": 498,
        "total": 576,
    }
    assert candidate == {
        "accept_threshold": 0.35,
        "is_active": False,
        "margin_threshold": 0.17,
        "satisfies_calibration_safety_target": True,
        "top_k_contexts": 2,
    }
    assert config["global"] == {
        "accept_threshold": candidate["accept_threshold"],
        "margin_threshold": candidate["margin_threshold"],
        "top_k_contexts": candidate["top_k_contexts"],
    }
    assert config["evaluation_run_id"] == result["evaluation_run_id"]
    assert not config["is_active"]
    assert not result["activation_recommended"]
    assert not result["activation_gates"]["labels_human_reviewed"]


def test_phase4_svg_and_notebook_are_valid():
    ET.parse(ROOT / "data" / "phase4_threshold_tradeoff.svg")
    notebook = json.loads(
        (ROOT / "notebooks" / "threshold_exploration.ipynb").read_text(
            encoding="utf-8"
        )
    )

    assert notebook["nbformat"] == 4
    assert any(
        "phase4_threshold_tradeoff.svg" in "".join(cell.get("source", []))
        for cell in notebook["cells"]
    )


def test_supabase_candidate_record_is_explicitly_inactive():
    operation = (
        ROOT
        / "supabase"
        / "operations"
        / "20261017_record_phase4_candidate.sql"
    ).read_text(encoding="utf-8")

    assert "032997a7-2c9d-5d32-889e-b93b70295c12" in operation
    assert "f0746f95-0581-53ca-ac9f-fd67d5c16100" in operation
    assert "0.35" in operation
    assert "0.17" in operation
    assert "is_active = false" in operation


def test_live_supabase_verification_confirms_candidate_is_inactive():
    verification = json.loads(
        (ROOT / "data" / "phase4_supabase_verification.json").read_text(
            encoding="utf-8"
        )
    )

    assert not verification["candidate_threshold"]["is_active"]
    assert verification["candidate_threshold"]["accept_threshold"] == 0.35
    assert verification["candidate_threshold"]["margin_threshold"] == 0.17
    assert all(
        check["matches_expected"]
        for check in verification["checks"].values()
    )
