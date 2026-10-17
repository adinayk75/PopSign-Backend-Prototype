-- Read-only verification for the completed Phase 3 MPNet embedding run.
-- Every returned row must have matches = true.

with sample as (
    select w.word_key, pe.embedding
    from public.popsign_phrase_embeddings pe
    join public.popsign_word_phrases wp on wp.id = pe.word_phrase_id
    join public.popsign_words w on w.id = wp.word_id
    join public.popsign_variant_contexts vc
      on vc.word_phrase_id = wp.id
     and vc.matching_eligible
    join public.popsign_sign_variants sv
      on sv.id = vc.variant_id
     and sv.is_active
     and sv.matching_eligible
    join public.popsign_word_match_readiness readiness
      on readiness.word_id = w.id
     and readiness.matching_ready
    where pe.embedding_model_id = 'ab922308-695a-50c2-ad75-9f5bd7c163a9'
    order by w.word_key
    limit 1
), live_matches as (
    select matched.*
    from sample
    cross join lateral public.popsign_match_context_phrases(
        sample.word_key,
        sample.embedding,
        'sentence-transformers/all-mpnet-base-v2',
        'hf-e8c3b32edf5434bc2275fc9bab85f82640a19130',
        5
    ) as matched
), checks(metric, actual, expected, matches) as (
    select
        'embedding_models',
        count(*)::text,
        '1',
        count(*) = 1
    from public.popsign_embedding_models
    where id = 'ab922308-695a-50c2-ad75-9f5bd7c163a9'
      and model_name = 'sentence-transformers/all-mpnet-base-v2'
      and model_version = 'hf-e8c3b32edf5434bc2275fc9bab85f82640a19130'
      and dimensions = 768
      and lifecycle_status = 'candidate'

    union all

    select
        'phrase_embeddings',
        count(*)::text,
        '11924',
        count(*) = 11924
    from public.popsign_phrase_embeddings
    where embedding_model_id = 'ab922308-695a-50c2-ad75-9f5bd7c163a9'

    union all

    select
        'distinct_word_phrases',
        count(distinct word_phrase_id)::text,
        '11924',
        count(distinct word_phrase_id) = 11924
    from public.popsign_phrase_embeddings
    where embedding_model_id = 'ab922308-695a-50c2-ad75-9f5bd7c163a9'

    union all

    select
        'distinct_source_hashes',
        count(distinct source_hash)::text,
        '11924',
        count(distinct source_hash) = 11924
    from public.popsign_phrase_embeddings
    where embedding_model_id = 'ab922308-695a-50c2-ad75-9f5bd7c163a9'

    union all

    select
        'wrong_dimensions',
        count(*)::text,
        '0',
        count(*) = 0
    from public.popsign_phrase_embeddings
    where embedding_model_id = 'ab922308-695a-50c2-ad75-9f5bd7c163a9'
      and dimensions <> 768

    union all

    select 'live_match_rows', count(*)::text, '5', count(*) = 5
    from live_matches

    union all

    select
        'top_match_similarity',
        round(max(similarity)::numeric, 6)::text,
        '1.000000',
        round(max(similarity)::numeric, 6) = 1
    from live_matches

    union all

    select
        'import_run_phase',
        phase,
        'embeddings_complete',
        phase = 'embeddings_complete'
    from public.popsign_import_runs
    where id = '1fe293ca-0f74-5811-8a87-fcc5e23f21ad'
)
select metric, actual, expected, matches
from checks
order by metric;
