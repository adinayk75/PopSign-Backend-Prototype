import json

import pytest

from src.context_bank import (
    ContextBank,
    ContextBankError,
    WorkbookRow,
    build_import_payload,
    reconcile_with_audit,
)


def sample_bank() -> ContextBank:
    return ContextBank(
        source_name="context_bank.xlsx",
        workbook_sha256="a" * 64,
        sheet_name="Example Organized",
        rows=(
            WorkbookRow(
                3,
                "Books",
                "Can",
                "",
                "A shared sentence. || She can cook.",
                "can.1.1",
                "ABLE",
                "",
                "-",
                "",
            ),
            WorkbookRow(
                4,
                "Books",
                "can",
                "",
                "A shared sentence. || Open the can.",
                "can.2.1",
                "",
                "CONTAINER",
                "Use This",
                "",
            ),
            WorkbookRow(
                5,
                "Books",
                "can",
                "",
                "",
                "can.2.1",
                "",
                "",
                "Duplicate Word(s)",
                "duplicate source row",
            ),
            WorkbookRow(
                6,
                "Other",
                "Cat",
                "",
                "The cat naps.",
                "cat.1.1",
                "",
                "",
                "Remove This",
                "",
            ),
        ),
    )


def test_payload_preserves_rows_and_merges_only_the_variant_identity():
    payload = build_import_payload(sample_bank())

    assert payload.summary["source_rows"] == 4
    assert payload.summary["words"] == 2
    assert payload.summary["sign_variants"] == 3
    assert payload.summary["variant_contexts"] == 5
    assert payload.summary["phrases"] == 4
    assert payload.summary["word_phrases"] == 4
    assert payload.summary["variant_tags"] == 2
    assert payload.summary["active_source_rows"] == 2
    assert payload.summary["active_sign_variants"] == 2

    source_rows = payload.tables["popsign_source_rows"]
    assert len(source_rows) == 4
    assert source_rows[2]["is_duplicate_pair"] is True
    assert source_rows[2]["duplicate_of_source_row_id"] == source_rows[1]["id"]


def test_shared_active_context_is_retained_but_blocked_from_matching():
    payload = build_import_payload(sample_bank())
    contexts = payload.tables["popsign_variant_contexts"]

    shared = [row for row in contexts if row["shared_across_active_variants"]]
    unique = [
        row
        for row in contexts
        if row["eligibility_reason"] == "unique_to_active_variant"
    ]
    inactive = [row for row in contexts if row["eligibility_reason"] == "inactive_source"]

    assert len(shared) == 2
    assert all(row["matching_eligible"] is False for row in shared)
    assert len(unique) == 2
    assert all(row["matching_eligible"] is True for row in unique)
    assert len(inactive) == 1
    assert payload.summary["words_matching_ready"] == 1


def test_ids_and_payload_are_deterministic():
    first = build_import_payload(sample_bank())
    second = build_import_payload(sample_bank())

    assert first == second


def test_audit_reconciliation_reports_any_count_or_hash_drift():
    payload = build_import_payload(sample_bank())
    summary = payload.summary
    audit = {
        "source": {"data_rows": summary["source_rows"], "sha256": "a" * 64},
        "coverage": {
            "unique_words_case_insensitive": summary["words"],
            "unique_video_keys_case_insensitive": summary["sign_variants"],
            "unique_context_strings_case_insensitive": summary["phrases"],
            "unique_word_context_pairs": summary["word_phrases"],
            "context_phrase_assignments": summary["variant_contexts"],
            "exact_tag_assignments": summary["exact_tag_assignments"],
            "near_tag_assignments": summary["near_tag_assignments"],
        },
        "existing_active_status_policy": {
            "active_rows": summary["active_source_rows"],
            "active_unique_video_keys": summary["active_sign_variants"],
        },
        "recording_status_counts": summary["recording_status_counts"],
    }
    reconcile_with_audit(payload, audit)

    changed = json.loads(json.dumps(audit))
    changed["source"]["data_rows"] += 1
    with pytest.raises(ContextBankError, match="does not reconcile"):
        reconcile_with_audit(payload, changed)
