from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "202610030001_vector_store.sql"


def test_migration_enables_vector_storage_and_safe_access():
    sql = MIGRATION.read_text().lower()

    assert "create extension if not exists vector" in sql
    assert "extensions.vector(768)" in sql
    assert "create or replace function public.match_context_phrases" in sql
    assert "enable row level security" in sql
    assert "revoke all" in sql
    assert "grant execute" in sql
