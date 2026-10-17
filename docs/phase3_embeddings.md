# Phase 3: Production-Candidate Embeddings

Phase 3 creates one real semantic vector for every target-word/phrase pair in
the complete PopSign context bank and stores those vectors in Supabase. It does
not use a ten-word sample or the deterministic hashing demo.

## Completed result

| Item | Verified value |
| --- | --- |
| Workbook rows covered | 2,442 |
| Word-phrase pairs embedded | 11,924 |
| Distinct stored word-phrase IDs | 11,924 |
| Distinct embedding source hashes | 11,924 |
| Model | `sentence-transformers/all-mpnet-base-v2` |
| Immutable model revision | `e8c3b32edf5434bc2275fc9bab85f82640a19130` |
| Dimensions | 768 |
| Normalization | L2-normalized |
| Stored lifecycle | `candidate` |
| Supabase import batches | 12 |

The prompt is target-word aware:

```text
Meaning of "{target_word}" in this sentence: {context_text}
```

This matters because one sentence can be associated with several vocabulary
words. The target word, model name, model revision, dimensions, prompt template,
and exact context are included in each deterministic source hash.

## Provider decision

The production-candidate run uses the public MPNet sentence-transformer model.
It produces the schema's required 768 dimensions and can be reproduced without
a gated-model credential. EmbeddingGemma remains supported, but it requires an
accepted license, a Hugging Face token, and an explicitly pinned revision.

The hashing provider is retained only for fast local UI and unit tests. The
production uploader refuses hashing vectors by default, and none were uploaded
to the real project.

## Reproducible generation

Install the optional model dependencies and validate the complete workbook:

```bash
uv sync --extra ml --group dev
uv run python scripts/embed_context_bank.py \
  --workbook /absolute/path/to/context_bank.xlsx \
  --provider mpnet \
  --batch-size 1000
```

With a locally configured Supabase server secret, add `--apply` for resumable
API upserts. Without that key, generate authenticated-dashboard import files:

```bash
uv run python scripts/export_context_bank_embeddings.py \
  --workbook /absolute/path/to/context_bank.xlsx \
  --provider mpnet \
  --batch-size 1000
```

The exporter writes a private manifest, one model row, and bounded CSV batches
under ignored `.popsign-state/`. It records a SHA-256 for every file and an
`uploaded` flag for every confirmed batch. Re-running it verifies existing
files and resumes instead of regenerating completed work.

## Live Supabase verification

The final database-side reconciliation passed all of these checks:

- exactly one matching model record with the pinned revision;
- exactly 11,924 embedding records;
- exactly 11,924 distinct word-phrase IDs;
- exactly 11,924 distinct source hashes;
- zero records with the wrong dimensions;
- five results returned by the live matching RPC for a matching-ready word;
- a cosine similarity of `1.000000` for the stored phrase used as its own query;
- import run phase updated to `embeddings_complete`.

The public-safe result is stored in
`data/phase3_embedding_verification.json`. The exact read-only reconciliation
query is in `supabase/verification/20261017_phase3_embeddings.sql`. The private
workbook, generated vectors, dashboard CSVs, credentials, and checkpoints
remain outside Git.

## What Phase 4 still decides

The model stays in `candidate` status. Phase 4 needs human-labeled positive,
negative, and ambiguous phrases to measure accuracy and coverage, then choose a
global acceptance threshold plus runner-up margin. Per-word overrides should be
added only where enough reviewed examples show that the global rule is not
adequate. Hardware video paths remain a separate manifest keyed by
`video_key`; video files are not stored in Supabase.
