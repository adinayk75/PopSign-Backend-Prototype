# Full Context Bank Audit

Phase 1 audited every populated row in the complete source workbook. It did not create a sample database, change Supabase, generate embeddings, or upload any private source data.

## Scope and verification

- One worksheet with 2 header rows and 2,442 populated data rows.
- Nine source fields per row: source, word, definition, context, video reference, exact tags, near tags, recording status, and notes.
- No hidden sheets, hidden rows or columns, or formulas.
- Workbook SHA-256: `77b843062e7151ab8c94a2449bdfd49c74b2c7c7c4b81fce655b0ec3f043b1a3`.
- The artifact-tool audit and an independent read-only pandas check agreed on row counts, status counts, active rows, context-ready ambiguous words, and pairwise-disjoint words.
- The source workbook is intentionally not committed because this repository is public.

## Complete workbook inventory

| Measure | Result |
| --- | ---: |
| Populated source rows | 2,442 |
| Unique words | 1,748 |
| Unique video references | 2,436 |
| Context phrase assignments | 17,450 |
| Unique context strings | 5,838 |
| Unique word-context pairs | 11,924 |
| Exact-tag assignments | 627 |
| Near-tag assignments | 317 |
| Words with multiple video references | 482 |

Repeated context strings across different words are expected because one story sentence can contain several vocabulary words. The audit found no duplicated context assignment inside the same word-video combination.

## Data completeness

| Field | Populated rows | Coverage |
| --- | ---: | ---: |
| Word | 2,442 | 100.0% |
| Video reference | 2,442 | 100.0% |
| Recording status | 2,406 | 98.5% |
| Context | 1,574 | 64.5% |
| Exact tags | 618 | 25.3% |
| Near tags | 301 | 12.3% |
| Notes | 595 | 24.4% |
| Definition | 0 | 0.0% |
| At least one definition, tag, or note | 1,186 | 48.6% |

The definition column is present but empty for every row. Definitions and human-readable sense labels therefore need to be generated, versioned, and reviewed later; the importer must not invent them silently.

## Recording statuses

All 2,442 rows should be preserved in Supabase. Recording status should control matching eligibility, not whether a row is stored.

| Existing status | Rows |
| --- | ---: |
| Default marker | 2,007 |
| Remove | 261 |
| Needs filming | 70 |
| Use | 43 |
| Blank | 36 |
| Duplicate | 23 |
| Already in the smaller reference set | 2 |

The existing active policy treats the default marker, use status, and existing-reference status as matchable. Under that policy there are 2,052 active rows, 1,508 active words, and 2,051 active video references. The production schema should store the original status and a separate reviewed `matching_eligible` flag.

## Main matching-quality finding

There are 388 active words with multiple video variants:

- 254 have context for every active variant.
- 6 have context for only some variants.
- 128 have no context on any active variant.

Among the 254 active words that appear context-ready:

- Only **11** have pairwise-disjoint context sets.
- **243** reuse at least one context across different video variants.
- **229** have identical context sets for at least one pair of variants.

This means 95.7% of the currently context-ready ambiguous words contain overlapping evidence. Embedding the workbook exactly as it stands would often give multiple variants the same evidence, so cosine similarity could not reliably choose between them. The production import should preserve these contexts but mark copied or unresolved contexts as unavailable for matching until sense-specific examples are created or approved.

## Video-reference readiness

Every row has a video reference, but the workbook contains logical identifiers rather than physical hardware paths:

| Format | Rows |
| --- | ---: |
| `base.number.number` | 2,208 |
| Bare legacy identifier | 219 |
| `base.number` | 3 |
| Unrecognized format | 12 |
| File path or video filename | 0 |

Six word-video combinations appear twice and require merge/review. Twelve rows contain video-reference formatting that does not fit any established pattern. The production database should preserve the original reference and assign a separate canonical `video_key`. A later hardware manifest will map that canonical key to the actual file.

## Actionable cleanup

| Issue | Affected rows |
| --- | ---: |
| Missing definition | 2,442 |
| Missing context | 868 |
| Context shared across video variants | 736 rows across 297 words |
| Missing recording status | 36 |
| Repeated spaces | 42 |
| Unrecognized video-reference format | 12 |
| Duplicate word-video pair | 6 duplicate rows |

The six duplicate row groups are `188/210`, `368/369`, `573/574`, `773/774`, `1529/1535`, and `1648/1649`. Exact row lists for the other small exception groups are in `data/context_bank_audit.json`.

The audit found zero rows with a missing word, missing video reference, missing source, malformed context delimiter, exact duplicate full row, exact/near tag overlap, or duplicate phrase assignment within the same word-video combination.

## Required production import behavior

1. Import all 2,442 source rows. Do not build a reduced-word Supabase database.
2. Preserve both raw and normalized values.
3. Split context cells into 17,450 phrase assignments while retaining workbook row lineage.
4. Store inactive, duplicate, removal, missing-video, and unresolved states rather than discarding those rows.
5. Keep `matching_eligible` separate from recording and import status.
6. Do not treat a context shared between variants as valid sense-selection evidence by default.
7. Generate definitions, sense labels, and replacement context examples as versioned reviewable records.
8. Preserve the legacy video reference and create a stable canonical `video_key`.
9. Map `video_key` to hardware filenames through a separate manifest; do not store video binaries in Supabase.
10. Attach the source workbook hash, source row, and import-run identifier to every record.
11. Make every import batch idempotent and resumable.

## Phase 1 decision

The workbook is structurally importable in full. The next phase should finalize a production schema that can hold every source row and its review state. It should not send the current pilot catalog to the real Supabase project.
