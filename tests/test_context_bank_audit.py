import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_JSON = ROOT / "data" / "context_bank_audit.json"
AUDIT_DOC = ROOT / "docs" / "context_bank_audit.md"


def load_audit() -> dict:
    return json.loads(AUDIT_JSON.read_text())


def test_audit_covers_the_complete_workbook():
    audit = load_audit()
    rows = audit["source"]["data_rows"]

    assert audit["scope"] == "Every populated data row in the complete source workbook"
    assert rows == 2_442
    assert sum(audit["recording_status_counts"].values()) == rows
    assert audit["completeness"]["rows_with_context"] + audit["completeness"]["rows_without_context"] == rows
    assert sum(audit["video_key_formats"].values()) == rows


def test_audit_matching_coverage_reconciles():
    audit = load_audit()
    active = audit["active_ambiguous_word_coverage"]
    all_rows = audit["all_status_ambiguous_word_coverage"]

    assert active["all_variants_have_context"] + active["some_but_not_all_variants_have_context"] + active["no_variants_have_context"] == active["words_with_multiple_active_video_keys"]
    assert active["pairwise_disjoint_contexts"] + active["overlapping_contexts"] == active["words_with_at_least_two_context_bearing_variants"]
    assert all_rows["all_variants_have_context"] + all_rows["some_but_not_all_variants_have_context"] + all_rows["no_variants_have_context"] == all_rows["words_with_multiple_video_keys"]
    assert all_rows["pairwise_disjoint_contexts"] + all_rows["overlapping_contexts"] == all_rows["words_with_at_least_two_context_bearing_variants"]


def test_public_audit_does_not_copy_private_rows():
    audit = load_audit()

    assert audit["source"]["source_workbook_committed"] is False
    assert audit["privacy"]["raw_context_phrases_in_report"] is False
    assert audit["privacy"]["raw_word_rows_in_report"] is False
    assert audit["privacy"]["raw_video_key_values_in_report"] is False
