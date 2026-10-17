# Phase 4: Threshold Evaluation

Phase 4 evaluates the exact pinned MPNet vectors uploaded in Phase 3. It does
not activate a production threshold. The current labels and video-to-sense
mappings still require PopSign ASL-team review.

## Evaluation design

The run contains **576 cases** across 15 production words with multiple usable
video variants:

| Case source | Cases | Purpose |
|---|---:|---|
| Source leave-one-out and shared contexts | 498 | Test existing workbook assignments without allowing an exact phrase to match itself; treat phrases assigned to multiple active variants as ambiguous. |
| LLM-generated candidate phrases | 78 | Test unseen `about`, `can`, and `love` sentences across six proposed senses, including deliberately ambiguous examples. |
| Calibration split | 376 | Select a candidate rule. |
| Untouched holdout split | 200 | Measure the selected rule once after selection. |

The checked-in LLM dataset contains no private workbook phrases or legacy video
references. Its six production video mappings, raw results, review sheets, and
query-embedding checkpoint stay under ignored `.popsign-state/phase4/` files.

The evaluator tests:

- accept thresholds from 0.35 through 0.95;
- runner-up margins from 0.00 through 0.40;
- averages of the strongest 1, 2, 3, or 5 reference contexts;
- a minimum 95% accepted precision target; and
- a minimum 90% ambiguous-rejection target.

## Candidate result

The strongest conservative calibration candidate is:

| Setting | Candidate |
|---|---:|
| Cosine accept threshold | **0.35** |
| Runner-up margin | **0.17** |
| Reference contexts averaged | **2** |
| Active | **No** |

Holdout performance:

| Metric | Result |
|---|---:|
| Accepted precision | **95.8%** |
| Positive coverage | **40.2%** |
| Ambiguous rejection | **90.3%** |
| Raw top-ranking accuracy on positive cases | **82.8%** |

The rule is safe enough to keep as a baseline, but not useful enough to
activate: it sends almost 60% of otherwise correct positive phrases to review.
On the harder LLM-only holdout, accepted precision is 80.0%, positive coverage
is 22.2%, and ambiguous rejection is 83.3%.

The completed evaluation and inactive threshold candidate were recorded in
Supabase on 2026-10-17. Five live checks confirmed the evaluation row, exact
candidate values, inactive status, absence of an active global threshold, and
the embedding model's `candidate` lifecycle. The public-safe verification is
in `data/phase4_supabase_verification.json`.

## What this says about cosine similarity

The raw top score is not a reliable confidence signal here. Ambiguous holdout
phrases have a median top cosine score around 0.81, while positive phrases have
a median around 0.86. The distributions overlap heavily because all candidates
share the same target word and many source contexts are copied or nearly
identical across variants.

The runner-up margin is more informative. Raising it improves precision and
ambiguous rejection, but sharply reduces coverage. The trade-off is recorded in
`data/phase4_threshold_tradeoff.svg` and in the notebook.

## Global versus per-word thresholds

Candidate overrides were explored for `about`, `can`, and `love`. They fit the
small calibration samples but did not generalize reliably to holdout cases.
Phase 4 therefore keeps one inactive global baseline and recommends **no
per-word overrides yet**. A word-specific override should require enough
human-reviewed positive and ambiguous cases to show a repeatable holdout gain.

## Activation blockers

The candidate stays inactive because:

1. none of the 576 labels has completed ASL-team review;
2. overall positive coverage is below the 60% usefulness target;
3. LLM-only holdout precision is below 95%; and
4. LLM-only ambiguous rejection is below 90%.

The review package contains 78 generated phrase labels plus six proposed
video-to-sense mappings. After review, rerun the same command. If the results
still fail, the next improvement should be differentiated reference contexts
for each sign variant, not a looser threshold.

## Reproduce or resume

```bash
uv sync --extra ml --group dev
uv run python scripts/evaluate_production_thresholds.py
```

The 78 generated query vectors are checkpointed by dataset hash and exact model
version. An interrupted rerun resumes from that checkpoint. Public-safe results
are in `data/phase4_threshold_evaluation.json`; the full case-level output and
review CSVs remain outside Git.
