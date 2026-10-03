# Storage Decision: Supabase + Local Videos

## Decision

Use Supabase Postgres for words, sign meanings, context phrases, configuration, and vector embeddings. Keep the actual ASL video files in the existing local video collection for this prototype and reference them with `video_key`.

## Why this fits the current work

- Supabase uses PostgreSQL and supports `pgvector`, so metadata and embeddings stay together.
- A phrase can be linked to one provisional sign meaning and one local video key.
- SQL constraints prevent orphaned meanings and context examples.
- The `match_context_phrases` database function can filter by word before calculating cosine similarity.
- Model name, model version, vector dimension, and source hash are stored with every embedding.
- The browser never receives the server secret key.

## Current split

```text
Supabase
  words
  sign_senses
  context_phrases
  phrase_embeddings
  matching_config
        |
        v
Python matching API
        |
        v
local video_key (for example: demo/can/ability.mp4)
```

## Why not put videos in the database?

Video files are much larger than metadata and numeric vectors. Storing only a stable `video_key` keeps the vector query small and preserves the team's existing local video workflow. Object storage can be reconsidered later without changing the matcher response.

## Earlier alternatives

The first prototype compared DynamoDB + S3, PostgreSQL, and JSON. JSON remains useful for credential-free local testing, but Supabase is now the selected shared data layer because vector search is a first-class requirement.
