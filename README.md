# PopSign Backend Prototype

A testable prototype for choosing the correct ASL video when a generated story contains a word with multiple meanings.

The current pilot demonstrates six provisional meanings across three words:

- `can`: ability vs. container
- `about`: approximate amount/time vs. topic
- `love`: affection for a person/animal vs. enjoyment of a thing/activity

The Georgia Tech PopSign repository was used only as a read-only source reference. This personal repository contains the prototype implementation.

## What the demo proves

```text
story phrase
    -> generate a normalized 768-D embedding
    -> retrieve stored phrase embeddings for the target word
    -> calculate cosine similarity
    -> compare the winner with both a score threshold and runner-up margin
    -> return an ASL video key or flag the phrase for review
```

It intentionally does **not** silently choose a default video when the context is unclear.

## Quick local demo

Requirements: Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --group dev
uv run uvicorn src.api:app --reload
```

Open <http://127.0.0.1:8000>.

The default `local` backend requires no keys or model download. It uses a deterministic 768-dimensional hashing baseline so the complete product flow can be demonstrated immediately. It is clearly separated from the optional EmbeddingGemma provider and should not be treated as the final semantic model.

## Supabase setup

The current migration and seeder belong to the local three-word prototype. **Do not run the pilot seeder against the real PopSign Supabase project.** Production setup is paused until the full-workbook schema and importer are completed.

Phase 1 audited the complete source workbook rather than a small sample:

- 2,442 source rows
- 1,748 unique words
- 17,450 context-phrase assignments
- 482 words with multiple video references

See [`docs/context_bank_audit.md`](docs/context_bank_audit.md) for the complete public-safe findings and [`docs/supabase_setup.md`](docs/supabase_setup.md) for the current connection status.

## Optional local EmbeddingGemma demo

This still uses the synthetic three-word catalog and must not point at the production Supabase project.

```bash
uv sync --extra ml --group dev
uv run python scripts/seed_supabase.py --provider embeddinggemma
```

Then set:

```dotenv
POPSIGN_EMBEDDING_PROVIDER=embeddinggemma
```

If the model is not cached, set `GEMMA_TOKEN` locally. Never commit it.

## Test and evaluate

```bash
uv run pytest -q
uv run python scripts/seed_supabase.py --dry-run
uv run python scripts/evaluate_thresholds.py
```

The threshold script and [`notebooks/threshold_exploration.ipynb`](notebooks/threshold_exploration.ipynb) evaluate a global acceptance threshold plus a runner-up margin. Current labels and thresholds are provisional until reviewed by the PopSign ASL team.

## Main files

```text
data/pilot_catalog.json               reviewed-data staging format
data/context_bank_audit.json          public-safe full-workbook audit metrics
src/embeddings.py                     hashing + EmbeddingGemma providers
src/vector_matcher.py                 cosine scoring and acceptance rule
src/api.py                            FastAPI endpoints and static demo
scripts/seed_supabase.py              pilot-only versioned demo seeder
scripts/evaluate_thresholds.py        repeatable threshold experiment
supabase/migrations/...sql            pgvector schema and match RPC
web/                                  Figma-inspired mobile test frontend
tests/                                baseline, vector, API, and schema tests
docs/context_bank_audit.md            Phase 1 production-data findings
```

## Important review boundary

The committed catalog uses synthetic phrases and placeholder video paths so this public repository does not expose the private PopSign context bank. Every record remains marked `human_approved: false`. The software architecture is ready to test, but approved private labels and video mappings must be imported separately before production use.

The synthetic catalog is retained only for local automated tests and UI demonstrations. It is not the planned content of the production Supabase database. The production importer will process every valid row in the full private workbook and store inactive or unresolved rows with explicit statuses rather than silently dropping them.
