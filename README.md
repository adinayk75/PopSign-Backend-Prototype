# PopSign Backend Prototype

A proof of concept for selecting the correct ASL video when a generated story contains a word with multiple meanings.

## Problem

A generated story can contain ambiguous vocabulary. For example, the word `rock` may mean a stone, a music genre, or the phrase `rock on`. PopSign needs to use the surrounding story context to select the ASL video that matches the intended meaning.

This prototype demonstrates that the contextual matching can happen directly in the backend without MCP.

## Prototype flow

```text
Generated story
    -> locate target vocabulary word
    -> collect candidate ASL sign records
    -> score each candidate against story context
    -> select the highest-scoring meaning
    -> return the matching video key/URL
```

The prototype uses a simple, deterministic tag-based scorer first because it is easy to explain, test, and integrate. The storage schema is designed so the same data can later support embedding similarity or an LLM fallback without changing the frontend contract.

## Recommended production storage

- **Amazon S3**: actual ASL video files
- **Amazon DynamoDB**: searchable metadata for each word/sense, including tags and the S3 object key

See [`docs/database_comparison.md`](docs/database_comparison.md) for the comparison and rationale.

## Repository structure

```text
.
├── README.md
├── data/
│   └── asl_signs.json
├── docs/
│   └── database_comparison.md
├── src/
│   ├── __init__.py
│   └── context_matcher.py
└── tests/
    └── test_context_matcher.py
```

## Run the demo

Requires Python 3.10+ and no third-party packages.

```bash
python3 src/context_matcher.py
```

Example result:

```text
Story: I listen to music. My favorite genre is rock.
Target word: rock
Selected sense: music
Selected video: asl/rock/music.mp4
```

## Run tests

```bash
python3 -m unittest discover -s tests -v
```

## Current matching strategy

For every candidate sign sense, the matcher compares normalized story words against that candidate's context tags. Exact tag hits receive the strongest weight, and a small phrase bonus is added when the sense label itself appears in the story. If there is no contextual evidence, the record marked as the default sense is returned.

This gives us a working backend contract now while leaving room for a later layered approach:

```text
exact/tag matching -> embedding similarity -> optional LLM fallback
```

## Next steps

1. Replace sample JSON records with the real PopSign ASL catalog.
2. Put video objects in S3 and metadata in DynamoDB.
3. Expose the matcher through the existing PopSign API layer.
4. Add embeddings if tag matching is not sufficient for real stories.
5. Validate ambiguous vocabulary against actual user-generated stories.
