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

1. Run [`supabase/migrations/202610030001_vector_store.sql`](supabase/migrations/202610030001_vector_store.sql) in the Supabase SQL Editor.
2. Copy `.env.example` to `.env` and add the project URL and server-only secret key.
3. Seed the pilot metadata and embeddings:

```bash
uv run python scripts/seed_supabase.py --provider hashing
```

4. Set `POPSIGN_DATA_BACKEND=supabase` in `.env` and restart the API.

See [`docs/supabase_setup.md`](docs/supabase_setup.md) for the safe step-by-step handoff.

## Optional EmbeddingGemma run

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
src/embeddings.py                     hashing + EmbeddingGemma providers
src/vector_matcher.py                 cosine scoring and acceptance rule
src/api.py                            FastAPI endpoints and static demo
scripts/seed_supabase.py              versioned embedding importer
scripts/evaluate_thresholds.py        repeatable threshold experiment
supabase/migrations/...sql            pgvector schema and match RPC
web/                                  Figma-inspired mobile test frontend
tests/                                baseline, vector, API, and schema tests
```

## Important review boundary

The committed catalog uses synthetic phrases and placeholder video paths so this public repository does not expose the private PopSign context bank. Every record remains marked `human_approved: false`. The software architecture is ready to test, but approved private labels and video mappings must be imported separately before production use.
