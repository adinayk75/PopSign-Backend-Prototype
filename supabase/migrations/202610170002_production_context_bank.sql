-- PopSign production context-bank schema.
--
-- This migration stores the complete private workbook while keeping video binaries
-- on PopSign workspace hardware. It intentionally uses popsign_* names so it can
-- coexist with the earlier three-word prototype tables during rollout.

create extension if not exists vector with schema extensions;
create extension if not exists pgcrypto with schema extensions;

create table if not exists public.popsign_import_runs (
    id uuid primary key,
    schema_version text not null,
    source_name text not null,
    worksheet_name text not null,
    workbook_sha256 text not null,
    source_row_count integer not null,
    status text not null default 'prepared',
    phase text not null default 'base_data',
    progress jsonb not null default '{}'::jsonb,
    payload_counts jsonb not null default '{}'::jsonb,
    error_message text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint popsign_import_runs_hash_format
        check (workbook_sha256 ~ '^[0-9a-f]{64}$'),
    constraint popsign_import_runs_source_rows_positive
        check (source_row_count > 0),
    constraint popsign_import_runs_status_valid
        check (status in ('prepared', 'importing', 'completed', 'failed')),
    unique (schema_version, workbook_sha256, worksheet_name)
);

create table if not exists public.popsign_words (
    id uuid primary key,
    word_key text not null unique,
    display_word text not null,
    review_status text not null default 'unreviewed',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint popsign_words_key_normalized
        check (word_key = lower(btrim(word_key)) and word_key <> '')
);

create table if not exists public.popsign_sign_variants (
    id uuid primary key,
    word_id uuid not null references public.popsign_words(id)
        on update cascade on delete restrict,
    video_key text not null unique,
    legacy_video_ref text not null,
    video_ref_key text not null,
    video_ref_format text not null,
    recording_status text not null,
    source_statuses jsonb not null default '[]'::jsonb,
    source_row_count integer not null default 1,
    sense_label text,
    definition text,
    is_active boolean not null default false,
    matching_eligible boolean not null default false,
    review_status text not null default 'unreviewed',
    human_approved boolean not null default false,
    reviewed_by text,
    reviewed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint popsign_sign_variants_ref_format_valid
        check (video_ref_format in (
            'base_number_number', 'base_number', 'bare_legacy_key', 'unrecognized'
        )),
    constraint popsign_sign_variants_recording_status_valid
        check (recording_status in (
            'missing', 'default', 'remove', 'needs_filming', 'use',
            'duplicate', 'existing_reference', 'mixed'
        )),
    constraint popsign_sign_variants_source_rows_positive
        check (source_row_count > 0),
    unique (word_id, video_ref_key)
);

create index if not exists popsign_sign_variants_word_idx
    on public.popsign_sign_variants(word_id);
create index if not exists popsign_sign_variants_active_idx
    on public.popsign_sign_variants(word_id, is_active, matching_eligible);

create table if not exists public.popsign_source_rows (
    id uuid primary key,
    import_run_id uuid not null references public.popsign_import_runs(id)
        on update cascade on delete restrict,
    source_row_number integer not null,
    row_fingerprint text not null,
    word_id uuid not null references public.popsign_words(id)
        on update cascade on delete restrict,
    variant_id uuid not null references public.popsign_sign_variants(id)
        on update cascade on delete restrict,
    raw_source text not null,
    source_key text not null,
    raw_word text not null,
    word_key text not null,
    raw_definition text not null default '',
    normalized_definition text,
    raw_context text not null default '',
    raw_video_ref text not null,
    video_ref_key text not null,
    raw_exact_tags text not null default '',
    raw_near_tags text not null default '',
    raw_recording_status text not null default '',
    recording_status text not null,
    raw_notes text not null default '',
    normalized_notes text,
    is_active_candidate boolean not null default false,
    context_count integer not null default 0,
    exact_tag_count integer not null default 0,
    near_tag_count integer not null default 0,
    is_duplicate_pair boolean not null default false,
    duplicate_of_source_row_id uuid references public.popsign_source_rows(id)
        on update cascade on delete restrict deferrable initially deferred,
    created_at timestamptz not null default now(),
    constraint popsign_source_rows_row_number_valid
        check (source_row_number >= 3),
    constraint popsign_source_rows_fingerprint_format
        check (row_fingerprint ~ '^[0-9a-f]{64}$'),
    constraint popsign_source_rows_counts_nonnegative
        check (context_count >= 0 and exact_tag_count >= 0 and near_tag_count >= 0),
    constraint popsign_source_rows_recording_status_valid
        check (recording_status in (
            'missing', 'default', 'remove', 'needs_filming', 'use',
            'duplicate', 'existing_reference'
        )),
    unique (import_run_id, source_row_number),
    unique (import_run_id, row_fingerprint)
);

create index if not exists popsign_source_rows_word_idx
    on public.popsign_source_rows(word_id);
create index if not exists popsign_source_rows_variant_idx
    on public.popsign_source_rows(variant_id);
create index if not exists popsign_source_rows_status_idx
    on public.popsign_source_rows(recording_status, is_active_candidate);

create table if not exists public.popsign_phrases (
    id uuid primary key,
    phrase_key text not null unique,
    context_text text not null,
    source_assignment_count integer not null default 1,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint popsign_phrases_key_present check (phrase_key <> ''),
    constraint popsign_phrases_assignment_count_positive
        check (source_assignment_count > 0)
);

create table if not exists public.popsign_word_phrases (
    id uuid primary key,
    word_id uuid not null references public.popsign_words(id)
        on update cascade on delete restrict,
    phrase_id uuid not null references public.popsign_phrases(id)
        on update cascade on delete restrict,
    source_assignment_count integer not null default 1,
    created_at timestamptz not null default now(),
    constraint popsign_word_phrases_assignment_count_positive
        check (source_assignment_count > 0),
    unique (word_id, phrase_id)
);

create index if not exists popsign_word_phrases_word_idx
    on public.popsign_word_phrases(word_id);
create index if not exists popsign_word_phrases_phrase_idx
    on public.popsign_word_phrases(phrase_id);

create table if not exists public.popsign_variant_contexts (
    id uuid primary key,
    variant_id uuid not null references public.popsign_sign_variants(id)
        on update cascade on delete restrict,
    word_phrase_id uuid not null references public.popsign_word_phrases(id)
        on update cascade on delete restrict,
    source_row_id uuid not null references public.popsign_source_rows(id)
        on update cascade on delete restrict,
    context_position integer not null,
    raw_context_text text not null,
    shared_across_variants boolean not null default false,
    shared_across_active_variants boolean not null default false,
    matching_eligible boolean not null default false,
    eligibility_reason text not null,
    review_status text not null default 'needs_review',
    human_approved boolean not null default false,
    reviewed_by text,
    reviewed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint popsign_variant_contexts_position_positive
        check (context_position > 0),
    constraint popsign_variant_contexts_reason_valid
        check (eligibility_reason in (
            'inactive_source', 'video_key_review',
            'shared_across_active_variants', 'unique_to_active_variant'
        )),
    unique (variant_id, word_phrase_id)
);

create index if not exists popsign_variant_contexts_variant_idx
    on public.popsign_variant_contexts(variant_id);
create index if not exists popsign_variant_contexts_word_phrase_idx
    on public.popsign_variant_contexts(word_phrase_id);
create index if not exists popsign_variant_contexts_matching_idx
    on public.popsign_variant_contexts(matching_eligible, variant_id);

create table if not exists public.popsign_tags (
    id uuid primary key,
    tag_kind text not null,
    tag_key text not null,
    display_tag text not null,
    review_status text not null default 'unreviewed',
    human_approved boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint popsign_tags_kind_valid check (tag_kind in ('exact', 'near')),
    constraint popsign_tags_key_present check (tag_key <> ''),
    unique (tag_kind, tag_key)
);

create table if not exists public.popsign_variant_tags (
    id uuid primary key,
    variant_id uuid not null references public.popsign_sign_variants(id)
        on update cascade on delete restrict,
    tag_id uuid not null references public.popsign_tags(id)
        on update cascade on delete restrict,
    source_row_id uuid not null references public.popsign_source_rows(id)
        on update cascade on delete restrict,
    tag_position integer not null,
    raw_tag_text text not null,
    review_status text not null default 'unreviewed',
    human_approved boolean not null default false,
    reviewed_by text,
    reviewed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint popsign_variant_tags_position_positive check (tag_position > 0),
    unique (variant_id, tag_id, source_row_id, tag_position)
);

create index if not exists popsign_variant_tags_variant_idx
    on public.popsign_variant_tags(variant_id);

create table if not exists public.popsign_embedding_models (
    id uuid primary key,
    model_name text not null,
    model_version text not null,
    provider_kind text not null,
    dimensions integer not null,
    prompt_template text not null,
    normalized boolean not null default true,
    lifecycle_status text not null default 'candidate',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint popsign_embedding_models_dimensions_768 check (dimensions = 768),
    constraint popsign_embedding_models_provider_valid
        check (provider_kind in ('hashing_demo', 'sentence_transformers')),
    constraint popsign_embedding_models_lifecycle_valid
        check (lifecycle_status in ('demo', 'candidate', 'active', 'retired')),
    unique (model_name, model_version, prompt_template)
);

create table if not exists public.popsign_phrase_embeddings (
    word_phrase_id uuid not null references public.popsign_word_phrases(id)
        on update cascade on delete restrict,
    embedding_model_id uuid not null references public.popsign_embedding_models(id)
        on update cascade on delete restrict,
    dimensions integer not null default 768,
    source_hash text not null,
    embedding extensions.vector(768) not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (word_phrase_id, embedding_model_id),
    constraint popsign_phrase_embeddings_dimensions_768 check (dimensions = 768),
    constraint popsign_phrase_embeddings_source_hash_format
        check (source_hash ~ '^[0-9a-f]{64}$')
);

create index if not exists popsign_phrase_embeddings_model_idx
    on public.popsign_phrase_embeddings(embedding_model_id);
create index if not exists popsign_phrase_embeddings_cosine_idx
    on public.popsign_phrase_embeddings
    using hnsw (embedding extensions.vector_cosine_ops);

create table if not exists public.popsign_hardware_devices (
    id uuid primary key default gen_random_uuid(),
    device_key text not null unique,
    display_name text not null,
    root_hint text,
    lifecycle_status text not null default 'active',
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint popsign_hardware_devices_status_valid
        check (lifecycle_status in ('active', 'offline', 'retired'))
);

create table if not exists public.popsign_video_assets (
    id uuid primary key default gen_random_uuid(),
    variant_id uuid not null references public.popsign_sign_variants(id)
        on update cascade on delete restrict,
    device_id uuid not null references public.popsign_hardware_devices(id)
        on update cascade on delete restrict,
    storage_kind text not null default 'workspace_hardware',
    relative_path text not null,
    file_name text not null,
    file_sha256 text,
    availability_status text not null default 'unverified',
    is_primary boolean not null default true,
    last_verified_at timestamptz,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint popsign_video_assets_storage_kind_valid
        check (storage_kind = 'workspace_hardware'),
    constraint popsign_video_assets_hash_format
        check (file_sha256 is null or file_sha256 ~ '^[0-9a-f]{64}$'),
    constraint popsign_video_assets_status_valid
        check (availability_status in ('unverified', 'available', 'missing', 'mismatch')),
    unique (device_id, relative_path)
);

create unique index if not exists popsign_video_assets_primary_variant_idx
    on public.popsign_video_assets(variant_id)
    where is_primary;

create table if not exists public.popsign_evaluation_runs (
    id uuid primary key default gen_random_uuid(),
    embedding_model_id uuid not null references public.popsign_embedding_models(id)
        on update cascade on delete restrict,
    dataset_name text not null,
    dataset_version text not null,
    strategy text not null,
    status text not null default 'running',
    metrics jsonb not null default '{}'::jsonb,
    notes text,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    constraint popsign_evaluation_runs_status_valid
        check (status in ('running', 'completed', 'failed'))
);

create table if not exists public.popsign_matching_thresholds (
    id uuid primary key default gen_random_uuid(),
    embedding_model_id uuid not null references public.popsign_embedding_models(id)
        on update cascade on delete restrict,
    scope_type text not null,
    word_id uuid references public.popsign_words(id)
        on update cascade on delete restrict,
    accept_threshold double precision not null,
    margin_threshold double precision not null,
    top_k_contexts integer not null default 3,
    evaluation_run_id uuid references public.popsign_evaluation_runs(id)
        on update cascade on delete restrict,
    is_active boolean not null default false,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint popsign_matching_thresholds_scope_valid
        check (scope_type in ('global', 'word')),
    constraint popsign_matching_thresholds_scope_word_consistent
        check (
            (scope_type = 'global' and word_id is null)
            or (scope_type = 'word' and word_id is not null)
        ),
    constraint popsign_matching_thresholds_accept_range
        check (accept_threshold between -1 and 1),
    constraint popsign_matching_thresholds_margin_range
        check (margin_threshold between 0 and 2),
    constraint popsign_matching_thresholds_top_k_range
        check (top_k_contexts between 1 and 20)
);

create unique index if not exists popsign_matching_thresholds_active_global_idx
    on public.popsign_matching_thresholds(embedding_model_id)
    where scope_type = 'global' and is_active;
create unique index if not exists popsign_matching_thresholds_active_word_idx
    on public.popsign_matching_thresholds(embedding_model_id, word_id)
    where scope_type = 'word' and is_active;

create table if not exists public.popsign_review_events (
    id uuid primary key default gen_random_uuid(),
    subject_type text not null,
    subject_id uuid not null,
    prior_status text,
    new_status text not null,
    decision text not null,
    reviewer text not null,
    notes text,
    created_at timestamptz not null default now(),
    constraint popsign_review_events_subject_type_valid
        check (subject_type in ('word', 'variant', 'context', 'tag', 'video_asset'))
);

create or replace function public.popsign_set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'popsign_import_runs',
        'popsign_words',
        'popsign_sign_variants',
        'popsign_phrases',
        'popsign_variant_contexts',
        'popsign_tags',
        'popsign_variant_tags',
        'popsign_embedding_models',
        'popsign_phrase_embeddings',
        'popsign_hardware_devices',
        'popsign_video_assets',
        'popsign_matching_thresholds'
    ]
    loop
        execute format(
            'drop trigger if exists %I on public.%I',
            table_name || '_set_updated_at',
            table_name
        );
        execute format(
            'create trigger %I before update on public.%I '
            || 'for each row execute function public.popsign_set_updated_at()',
            table_name || '_set_updated_at',
            table_name
        );
    end loop;
end;
$$;

create or replace view public.popsign_word_match_readiness
with (security_invoker = true)
as
with variant_counts as (
    select
        w.id as word_id,
        count(v.id) filter (where v.is_active) as active_variant_count,
        count(v.id) filter (
            where v.is_active and v.matching_eligible
        ) as eligible_variant_count
    from public.popsign_words w
    left join public.popsign_sign_variants v on v.word_id = w.id
    group by w.id
), evidence_counts as (
    select
        v.word_id,
        count(distinct vc.variant_id) filter (
            where v.is_active
              and v.matching_eligible
              and vc.matching_eligible
        ) as variants_with_eligible_context,
        count(vc.id) filter (
            where v.is_active
              and v.matching_eligible
              and vc.matching_eligible
        ) as eligible_context_count
    from public.popsign_sign_variants v
    left join public.popsign_variant_contexts vc on vc.variant_id = v.id
    group by v.word_id
)
select
    w.id as word_id,
    w.word_key,
    vc.active_variant_count,
    vc.eligible_variant_count,
    coalesce(ec.variants_with_eligible_context, 0) as variants_with_eligible_context,
    coalesce(ec.eligible_context_count, 0) as eligible_context_count,
    (
        vc.active_variant_count > 0
        and vc.active_variant_count = vc.eligible_variant_count
        and vc.active_variant_count = coalesce(ec.variants_with_eligible_context, 0)
    ) as matching_ready
from public.popsign_words w
join variant_counts vc on vc.word_id = w.id
left join evidence_counts ec on ec.word_id = w.id;

create or replace function public.popsign_match_context_phrases(
    p_target_word text,
    p_query_embedding extensions.vector(768),
    p_query_model_name text,
    p_query_model_version text,
    p_match_limit integer default 64
)
returns table (
    context_id uuid,
    context_text text,
    word text,
    video_key text,
    sense_label text,
    definition text,
    human_approved boolean,
    similarity double precision
)
language sql
stable
security invoker
set search_path = public, extensions
as $$
    select
        vc.id as context_id,
        p.context_text,
        w.word_key as word,
        sv.video_key,
        coalesce(sv.sense_label, 'Unreviewed meaning') as sense_label,
        coalesce(sv.definition, '') as definition,
        (sv.human_approved and vc.human_approved) as human_approved,
        1 - (pe.embedding <=> p_query_embedding) as similarity
    from public.popsign_phrase_embeddings pe
    join public.popsign_embedding_models em
      on em.id = pe.embedding_model_id
    join public.popsign_word_phrases wp
      on wp.id = pe.word_phrase_id
    join public.popsign_words w
      on w.id = wp.word_id
    join public.popsign_phrases p
      on p.id = wp.phrase_id
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
    where w.word_key = lower(btrim(p_target_word))
      and em.model_name = p_query_model_name
      and em.model_version = p_query_model_version
      and em.lifecycle_status in ('candidate', 'active')
    order by pe.embedding <=> p_query_embedding
    limit greatest(1, least(p_match_limit, 200));
$$;

create or replace function public.popsign_get_matching_threshold(
    p_target_word text,
    p_model_name text,
    p_model_version text
)
returns table (
    accept_threshold double precision,
    margin_threshold double precision,
    top_k_contexts integer,
    threshold_scope text
)
language sql
stable
security invoker
set search_path = public
as $$
    select
        mt.accept_threshold,
        mt.margin_threshold,
        mt.top_k_contexts,
        mt.scope_type as threshold_scope
    from public.popsign_matching_thresholds mt
    join public.popsign_embedding_models em
      on em.id = mt.embedding_model_id
    left join public.popsign_words w
      on w.id = mt.word_id
    where mt.is_active
      and em.model_name = p_model_name
      and em.model_version = p_model_version
      and (
          (mt.scope_type = 'word' and w.word_key = lower(btrim(p_target_word)))
          or mt.scope_type = 'global'
      )
    order by case when mt.scope_type = 'word' then 0 else 1 end
    limit 1;
$$;

alter table public.popsign_import_runs enable row level security;
alter table public.popsign_words enable row level security;
alter table public.popsign_sign_variants enable row level security;
alter table public.popsign_source_rows enable row level security;
alter table public.popsign_phrases enable row level security;
alter table public.popsign_word_phrases enable row level security;
alter table public.popsign_variant_contexts enable row level security;
alter table public.popsign_tags enable row level security;
alter table public.popsign_variant_tags enable row level security;
alter table public.popsign_embedding_models enable row level security;
alter table public.popsign_phrase_embeddings enable row level security;
alter table public.popsign_hardware_devices enable row level security;
alter table public.popsign_video_assets enable row level security;
alter table public.popsign_evaluation_runs enable row level security;
alter table public.popsign_matching_thresholds enable row level security;
alter table public.popsign_review_events enable row level security;

revoke all on table
    public.popsign_import_runs,
    public.popsign_words,
    public.popsign_sign_variants,
    public.popsign_source_rows,
    public.popsign_phrases,
    public.popsign_word_phrases,
    public.popsign_variant_contexts,
    public.popsign_tags,
    public.popsign_variant_tags,
    public.popsign_embedding_models,
    public.popsign_phrase_embeddings,
    public.popsign_hardware_devices,
    public.popsign_video_assets,
    public.popsign_evaluation_runs,
    public.popsign_matching_thresholds,
    public.popsign_review_events
from anon, authenticated;

revoke all on table public.popsign_word_match_readiness
from anon, authenticated;

revoke execute on function public.popsign_match_context_phrases(
    text, extensions.vector, text, text, integer
) from public, anon, authenticated;
revoke execute on function public.popsign_get_matching_threshold(
    text, text, text
) from public, anon, authenticated;

grant all on table
    public.popsign_import_runs,
    public.popsign_words,
    public.popsign_sign_variants,
    public.popsign_source_rows,
    public.popsign_phrases,
    public.popsign_word_phrases,
    public.popsign_variant_contexts,
    public.popsign_tags,
    public.popsign_variant_tags,
    public.popsign_embedding_models,
    public.popsign_phrase_embeddings,
    public.popsign_hardware_devices,
    public.popsign_video_assets,
    public.popsign_evaluation_runs,
    public.popsign_matching_thresholds,
    public.popsign_review_events
to service_role;

grant select on table public.popsign_word_match_readiness to service_role;
grant execute on function public.popsign_match_context_phrases(
    text, extensions.vector, text, text, integer
) to service_role;
grant execute on function public.popsign_get_matching_threshold(
    text, text, text
) to service_role;

-- No anon or authenticated policies are created. The browser must call the
-- Python API; only the server-side Supabase secret key can access private rows.
