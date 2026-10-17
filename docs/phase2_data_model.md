# Phase 2: Production Data Foundation

Phase 2 replaces the three-word storage placeholder with a production data model and importer for the complete private PopSign context bank. The workbook stays outside Git. The importer reads it locally and sends records directly to the server-side Supabase API.

## Verified full-workbook payload

The production dry run reconciles with the Phase 1 audit before Supabase can be contacted.

| Record type | Rows prepared |
| --- | ---: |
| Source workbook rows | 2,442 |
| Words | 1,748 |
| Sign variants | 2,436 |
| Unique phrases | 5,838 |
| Word-phrase pairs | 11,924 |
| Variant-context assignments | 17,450 |
| Unique typed tags | 923 |
| Variant-tag assignments | 944 |

All 2,442 source rows are preserved. A duplicate, removal status, missing recording status, missing context, or unresolved video reference changes review and matching eligibility; it does not remove the row from the import.

## Data flow

1. `popsign_import_runs` records the workbook hash, schema version, counts, status, and resumable progress.
2. `popsign_source_rows` stores every original field plus normalized lookup values and workbook-row lineage.
3. `popsign_words` groups case-insensitive vocabulary spellings.
4. `popsign_sign_variants` represents each word and legacy video-reference combination. It assigns a deterministic canonical `video_key` without changing the original reference.
5. `popsign_phrases` stores each unique context once.
6. `popsign_word_phrases` represents the target-word-specific version of a phrase. Embeddings attach here because the embedding prompt includes the target word.
7. `popsign_variant_contexts` connects each phrase to a sign variant and its exact workbook row.
8. `popsign_tags` and `popsign_variant_tags` preserve exact and near tags separately.
9. `popsign_embedding_models` and `popsign_phrase_embeddings` version every vector by model, model version, prompt template, dimensions, and source hash.
10. `popsign_hardware_devices` and `popsign_video_assets` map canonical video keys to hardware locations. They never store video bytes.
11. `popsign_evaluation_runs` and `popsign_matching_thresholds` support a global threshold plus reviewed per-word overrides without choosing the final strategy yet.

## Matching safety

The importer found 7,185 active context assignments whose phrase is shared by more than one active video variant for the same word. It stores these assignments but marks them unavailable to the matcher by default.

The remaining 7,619 active assignments are unique to one active variant. A word is exposed to vector matching only when every active variant has at least one eligible phrase. Under this conservative rule, 712 words are structurally ready. This does not mean their meanings are human-approved.

The `popsign_word_match_readiness` view enforces this rule. The `popsign_match_context_phrases` function returns only eligible evidence from a matching-ready word and the requested embedding model version.

## Safe local validation

The default command is read-only. It validates all 2,442 rows and prints counts only.

```bash
uv sync --group dev
uv run python scripts/import_context_bank.py \
  --workbook /absolute/path/to/context_bank.xlsx
```

The full deterministic embedding pipeline can be checked without Supabase:

```bash
uv run python scripts/embed_context_bank.py \
  --workbook /absolute/path/to/context_bank.xlsx \
  --provider hashing \
  --batch-size 500
```

The hashing provider validates all 11,924 vector records but remains a demo model. The embedding command refuses to upload it by default.

## Production import

Run the production migration in the Supabase SQL Editor first:

```text
supabase/migrations/202610170002_production_context_bank.sql
```

Keep `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `POPSIGN_CONTEXT_BANK_PATH` in the ignored local `.env` file. Then import the complete base dataset:

```bash
uv run python scripts/import_context_bank.py --apply
```

The importer upserts deterministic IDs in batches. After every successful batch it writes a private local checkpoint under `.popsign-state/`. If the process or Codex session stops, the same command resumes after the last confirmed batch. Re-running a completed import does not duplicate records.

Generate production-oriented embeddings only after the base import succeeds:

```bash
uv sync --extra ml --group dev
uv run python scripts/embed_context_bank.py \
  --provider mpnet \
  --apply
```

Embedding generation and upload are also batch-checkpointed. MPNet uses the
immutable revision recorded in Phase 3; EmbeddingGemma requires an explicitly
pinned revision and gated-model credentials. Model vectors cannot be mixed
silently because the model name, revision, prompt template, dimensions, and
source hash are part of the stored identity.

## Remaining human inputs

- Keep any future server secret only in the ignored local `.env` file.
- Review sense labels, definitions, and contexts. The source definition column is empty.
- Provide a hardware manifest that maps each canonical video key to an actual device and relative file path.
- Build labeled evaluation cases before activating global or per-word thresholds.

## Live completion

On 2026-10-17, the production migration and all nine base-data tables were
loaded into `popsign-demo`. A database-side query matched all expected source,
relationship, eligibility, and readiness counts. The result is recorded in
`data/phase2_supabase_verification.json`. Phase 3 subsequently loaded the
separate, versioned semantic embedding tables without changing this base-data
lineage; see `docs/phase3_embeddings.md`.
