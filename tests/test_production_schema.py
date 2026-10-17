from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "202610170002_production_context_bank.sql"


def test_production_migration_covers_the_complete_data_lifecycle():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    required_tables = {
        "popsign_import_runs",
        "popsign_words",
        "popsign_sign_variants",
        "popsign_source_rows",
        "popsign_phrases",
        "popsign_word_phrases",
        "popsign_variant_contexts",
        "popsign_tags",
        "popsign_variant_tags",
        "popsign_embedding_models",
        "popsign_phrase_embeddings",
        "popsign_hardware_devices",
        "popsign_video_assets",
        "popsign_evaluation_runs",
        "popsign_matching_thresholds",
        "popsign_review_events",
    }

    for table in required_tables:
        assert f"create table if not exists public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql

    assert "extensions.vector(768)" in sql
    assert "using hnsw (embedding extensions.vector_cosine_ops)" in sql
    assert "create or replace function public.popsign_match_context_phrases" in sql
    assert "create or replace view public.popsign_word_match_readiness" in sql
    assert "shared_across_active_variants" in sql
    assert "scope_type in ('global', 'word')" in sql
    assert "storage_kind = 'workspace_hardware'" in sql
    assert "grant execute" in sql
    assert "to service_role" in sql


def test_schema_stores_hardware_locations_but_not_video_blobs():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "relative_path text not null" in sql
    assert "file_sha256 text" in sql
    assert "video_data" not in sql
    assert "bytea" not in sql
