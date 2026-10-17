# Supabase Setup Status

> **Pilot warning:** Do not run `scripts/seed_supabase.py` against the real PopSign Supabase project. That command remains only for the synthetic three-word UI demo. Use the Phase 2 production migration and `scripts/import_context_bank.py` for the complete workbook.

## Already completed in the dashboard

- A Supabase project has been created.
- The `vector` extension has been enabled.

## Current project prerequisites

1. Open the project in Supabase.
2. Open **SQL Editor**.
3. Create a new query.
4. Run `supabase/migrations/202610170002_production_context_bank.sql`.

The production migration uses `popsign_*` table names, so it can coexist with the earlier three-word prototype during rollout.

## Configure backend access when the production migration is ready

From the repository:

```bash
cp .env.example .env
```

Open the Supabase project's **Connect** dialog or **Settings → API Keys**, then fill in these values locally:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=<server-secret-key>
```

Do not paste the secret key into chat, browser JavaScript, or GitHub. `.env` is ignored by Git.

## Validate the complete workbook first

Set the private local workbook path in `.env`:

```dotenv
POPSIGN_CONTEXT_BANK_PATH=/absolute/path/to/context_bank.xlsx
```

Run the read-only reconciliation:

```bash
uv sync --group dev
uv run python scripts/import_context_bank.py
```

Expected headline counts are 2,442 source rows, 1,748 words, 2,436 variants, 17,450 context assignments, and 11,924 word-specific phrases. Supabase is not contacted unless `--apply` is present.

## Import the complete database

After the production migration succeeds and the server credentials are configured:

```bash
uv run python scripts/import_context_bank.py --apply
```

This imports every row, including removals, duplicates, missing contexts, and unresolved states. It resumes from `.popsign-state/` after an interruption and uses deterministic upserts instead of creating duplicate records.

## Local prototype only

The following command prepares synthetic demo records. It must only be used for isolated local development, never for the real PopSign database:

```bash
uv sync --group dev
uv run python scripts/seed_supabase.py --provider hashing
```

Expected summary:

```text
Prepared 6 senses, 24 phrases, and 24 768-D embeddings.
```

The importer is idempotent: rerunning it updates the same versioned rows instead of creating duplicates.

## Production API connection

Change this line in `.env`:

```dotenv
POPSIGN_DATA_BACKEND=supabase
```

After the full importer has populated the project, run:

```bash
uv run uvicorn src.api:app --reload
```

Open <http://127.0.0.1:8000>. The Generate Story screen should report `supabase · 768-D vectors`.

## Generate the full EmbeddingGemma set

The complete context bank contains 11,924 unique target-word and phrase pairs. After the base data import:

```bash
uv sync --extra ml --group dev
export POPSIGN_EMBEDDING_MODEL_REVISION=<immutable-hugging-face-commit-sha>
uv run python scripts/embed_context_bank.py --provider embeddinggemma --apply
```

The command requires an immutable model revision, stores it with every vector set, and resumes after its last uploaded batch if interrupted. The hashing provider can validate all records locally, but the command blocks uploading those demo vectors unless an explicit test-only override is provided.

## Optional three-word demo: replace synthetic embeddings with EmbeddingGemma

This command still uses the three-word prototype catalog. Do not configure it with the production Supabase credentials.

```bash
uv sync --extra ml --group dev
uv run python scripts/seed_supabase.py --provider embeddinggemma
```

Then set `POPSIGN_EMBEDDING_PROVIDER=embeddinggemma` and restart the API. Use the same provider for both seeding and live queries; the database intentionally prevents the application from mixing model versions silently.

## Troubleshooting

- **RPC returns no rows:** confirm the same embedding provider seeded the database and is configured in `.env`.
- **Unauthorized:** confirm the Python backend—not the frontend—has the secret key.
- **Needs review:** the top match did not clear both the score threshold and runner-up margin. This is a valid safety result, not a crash.
- **Wrong video:** inspect the candidate evidence, then review the provisional sense labels before changing thresholds.
- **Project unavailable or paused:** restore the project in the Supabase dashboard, then rerun the same idempotent command.
- **Process interrupted:** rerun the same import command. The ignored `.popsign-state/` checkpoint resumes after the last confirmed batch.
