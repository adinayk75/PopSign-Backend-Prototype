-- Read-only Phase 4 verification. Every row should return matches_expected=true.

with checks as (
    select
        'evaluation_run'::text as check_name,
        count(*)::text as actual,
        '1'::text as expected
    from public.popsign_evaluation_runs
    where id = '032997a7-2c9d-5d32-889e-b93b70295c12'
      and status = 'completed'

    union all

    select
        'inactive_candidate_threshold',
        count(*)::text,
        '1'
    from public.popsign_matching_thresholds
    where id = 'f0746f95-0581-53ca-ac9f-fd67d5c16100'
      and is_active = false

    union all

    select
        'candidate_values',
        count(*)::text,
        '1'
    from public.popsign_matching_thresholds
    where id = 'f0746f95-0581-53ca-ac9f-fd67d5c16100'
      and accept_threshold = 0.35
      and margin_threshold = 0.17
      and top_k_contexts = 2

    union all

    select
        'active_global_thresholds',
        count(*)::text,
        '0'
    from public.popsign_matching_thresholds
    where embedding_model_id = 'ab922308-695a-50c2-ad75-9f5bd7c163a9'
      and scope_type = 'global'
      and is_active

    union all

    select
        'model_lifecycle',
        lifecycle_status,
        'candidate'
    from public.popsign_embedding_models
    where id = 'ab922308-695a-50c2-ad75-9f5bd7c163a9'
)
select
    check_name,
    actual,
    expected,
    actual = expected as matches_expected
from checks
order by check_name;
