-- Record the completed Phase 4 candidate evaluation without activating it.
-- This is idempotent and contains aggregate, public-safe metrics only.

insert into public.popsign_evaluation_runs (
    id,
    embedding_model_id,
    dataset_name,
    dataset_version,
    strategy,
    status,
    metrics,
    notes,
    started_at,
    completed_at
)
values (
    '032997a7-2c9d-5d32-889e-b93b70295c12',
    'ab922308-695a-50c2-ad75-9f5bd7c163a9',
    'phase4_source_plus_llm_candidate',
    '2026-10-17.1',
    'global_cosine_threshold_plus_runner_up_margin',
    'completed',
    jsonb_build_object(
        'case_counts', jsonb_build_object(
            'total', 576,
            'calibration', 376,
            'holdout', 200,
            'source_derived', 498,
            'llm_generated', 78,
            'positive', 486,
            'ambiguous', 90,
            'human_reviewed', 0
        ),
        'candidate', jsonb_build_object(
            'accept_threshold', 0.35,
            'margin_threshold', 0.17,
            'top_k_contexts', 2,
            'is_active', false
        ),
        'holdout', jsonb_build_object(
            'accepted_precision', 0.9577464788732394,
            'positive_coverage', 0.40236686390532544,
            'ambiguous_rejection_rate', 0.9032258064516129,
            'ranking_accuracy', 0.8284023668639053
        ),
        'activation_recommended', false
    ),
    'Inactive until PopSign ASL-team label review and usefulness gates pass.',
    '2026-10-17T17:56:10.894186+00:00',
    '2026-10-17T17:56:10.894186+00:00'
)
on conflict (id) do update set
    status = excluded.status,
    metrics = excluded.metrics,
    notes = excluded.notes,
    completed_at = excluded.completed_at;

insert into public.popsign_matching_thresholds (
    id,
    embedding_model_id,
    scope_type,
    word_id,
    accept_threshold,
    margin_threshold,
    top_k_contexts,
    evaluation_run_id,
    is_active,
    notes
)
values (
    'f0746f95-0581-53ca-ac9f-fd67d5c16100',
    'ab922308-695a-50c2-ad75-9f5bd7c163a9',
    'global',
    null,
    0.35,
    0.17,
    2,
    '032997a7-2c9d-5d32-889e-b93b70295c12',
    false,
    'Phase 4 conservative baseline; do not activate before ASL label review.'
)
on conflict (id) do update set
    accept_threshold = excluded.accept_threshold,
    margin_threshold = excluded.margin_threshold,
    top_k_contexts = excluded.top_k_contexts,
    evaluation_run_id = excluded.evaluation_run_id,
    is_active = false,
    notes = excluded.notes;
