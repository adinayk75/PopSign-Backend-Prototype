-- PopSign contextual phrase vector store
-- Run this file once in the Supabase SQL Editor.

create extension if not exists vector with schema extensions;

create table if not exists public.words (
    word text primary key,
    display_word text not null,
    review_status text not null default 'pilot',
    created_at timestamptz not null default now(),
    constraint words_lowercase check (word = lower(word))
);

create table if not exists public.sign_senses (
    video_key text primary key,
    word text not null references public.words(word) on update cascade on delete cascade,
    sense_label text not null,
    definition text not null,
    is_default boolean not null default false,
    review_status text not null,
    human_approved boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists sign_senses_word_idx
    on public.sign_senses(word);

create table if not exists public.context_phrases (
    context_id text primary key,
    video_key text not null references public.sign_senses(video_key) on update cascade on delete cascade,
    context_text text not null,
    source_type text not null,
    human_approved boolean not null default false,
    created_at timestamptz not null default now(),
    unique (video_key, context_text)
);

create index if not exists context_phrases_video_key_idx
    on public.context_phrases(video_key);

create table if not exists public.phrase_embeddings (
    context_id text not null references public.context_phrases(context_id) on update cascade on delete cascade,
    model_name text not null,
    model_version text not null,
    dimensions integer not null default 768,
    source_hash text not null,
    embedding extensions.vector(768) not null,
    created_at timestamptz not null default now(),
    primary key (context_id, model_name, model_version),
    constraint phrase_embeddings_dimensions check (dimensions = 768)
);

create index if not exists phrase_embeddings_model_idx
    on public.phrase_embeddings(model_name, model_version);

create table if not exists public.matching_config (
    config_key text primary key,
    accept_threshold double precision not null,
    margin_threshold double precision not null,
    top_k_contexts integer not null default 3,
    notes text,
    updated_at timestamptz not null default now(),
    constraint matching_config_accept_range check (accept_threshold between -1 and 1),
    constraint matching_config_margin_range check (margin_threshold between 0 and 2),
    constraint matching_config_top_k_range check (top_k_contexts between 1 and 20)
);

insert into public.matching_config (
    config_key,
    accept_threshold,
    margin_threshold,
    top_k_contexts,
    notes
)
values (
    'global',
    0.35,
    0.10,
    3,
    'Provisional demo values. Tune with labeled phrases before production use.'
)
on conflict (config_key) do nothing;

create or replace function public.match_context_phrases(
    p_target_word text,
    p_query_embedding extensions.vector(768),
    p_query_model_name text,
    p_query_model_version text,
    p_match_limit integer default 24
)
returns table (
    context_id text,
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
        cp.context_id,
        cp.context_text,
        ss.word,
        ss.video_key,
        ss.sense_label,
        ss.definition,
        ss.human_approved,
        1 - (pe.embedding <=> p_query_embedding) as similarity
    from public.phrase_embeddings pe
    join public.context_phrases cp on cp.context_id = pe.context_id
    join public.sign_senses ss on ss.video_key = cp.video_key
    where ss.word = lower(trim(p_target_word))
      and pe.model_name = p_query_model_name
      and pe.model_version = p_query_model_version
    order by pe.embedding <=> p_query_embedding
    limit greatest(1, least(p_match_limit, 100));
$$;

alter table public.words enable row level security;
alter table public.sign_senses enable row level security;
alter table public.context_phrases enable row level security;
alter table public.phrase_embeddings enable row level security;
alter table public.matching_config enable row level security;

-- The browser never talks to these tables directly in this prototype.
-- The Python API uses a server-only secret key. No anon policies are created.
revoke all on public.words from anon, authenticated;
revoke all on public.sign_senses from anon, authenticated;
revoke all on public.context_phrases from anon, authenticated;
revoke all on public.phrase_embeddings from anon, authenticated;
revoke all on public.matching_config from anon, authenticated;
revoke execute on function public.match_context_phrases(
    text,
    extensions.vector,
    text,
    text,
    integer
) from public, anon, authenticated;

grant all on public.words to service_role;
grant all on public.sign_senses to service_role;
grant all on public.context_phrases to service_role;
grant all on public.phrase_embeddings to service_role;
grant all on public.matching_config to service_role;
grant execute on function public.match_context_phrases(
    text,
    extensions.vector,
    text,
    text,
    integer
) to service_role;
