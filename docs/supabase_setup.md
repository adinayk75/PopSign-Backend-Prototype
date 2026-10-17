# Supabase Setup Status

> **Production hold:** Do not run `scripts/seed_supabase.py` against the real PopSign Supabase project. That command contains only the synthetic three-word prototype. The full-workbook audit is complete, but the production schema and complete importer belong to the next phases.

## Already completed in the dashboard

- A Supabase project has been created.
- The `vector` extension has been enabled.

## Current project prerequisites

1. Open the project in Supabase.
2. Open **SQL Editor**.
3. Create a new query.
4. Wait for the production migration that follows the full-workbook audit before creating the final tables.

The existing migration remains useful as prototype reference code, but it is not yet the approved full-data migration.

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

## Future production connection

Change this line in `.env`:

```dotenv
POPSIGN_DATA_BACKEND=supabase
```

After the full importer has populated the real project, run:

```bash
uv run uvicorn src.api:app --reload
```

Open <http://127.0.0.1:8000>. The Generate Story screen should report `supabase · 768-D vectors`.

## Optional local demo: replace synthetic embeddings with EmbeddingGemma

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
