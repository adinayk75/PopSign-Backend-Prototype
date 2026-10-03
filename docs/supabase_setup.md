# Supabase Setup for the PopSign Demo

## Already completed in the dashboard

- A Supabase project has been created.
- The `vector` extension has been enabled.

## Step 1: create the tables

1. Open the project in Supabase.
2. Open **SQL Editor**.
3. Create a new query.
4. Copy all of `supabase/migrations/202610030001_vector_store.sql` into the editor.
5. Click **Run** once.

The migration is repeatable. It creates five tables and one similarity-search function. It also enables Row Level Security and deliberately gives the browser no direct table access.

## Step 2: configure the backend locally

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

## Step 3: upload the pilot data and embeddings

For the immediate demo baseline:

```bash
uv sync --group dev
uv run python scripts/seed_supabase.py --provider hashing
```

Expected summary:

```text
Prepared 6 senses, 24 phrases, and 24 768-D embeddings.
```

The importer is idempotent: rerunning it updates the same versioned rows instead of creating duplicates.

## Step 4: make the API read from Supabase

Change this line in `.env`:

```dotenv
POPSIGN_DATA_BACKEND=supabase
```

Then run:

```bash
uv run uvicorn src.api:app --reload
```

Open <http://127.0.0.1:8000>. The Generate Story screen should report `supabase · 768-D vectors`.

## Optional: replace demo embeddings with EmbeddingGemma

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
