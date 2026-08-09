-- Vasuki AI V8 Foundation migration
-- Run once after the existing vasuki_memory_rag.sql migration.

create extension if not exists vector with schema extensions;

alter table public.user_memories
  add column if not exists normalized_text text,
  add column if not exists confidence double precision not null default 1.0,
  add column if not exists source text not null default 'explicit',
  add column if not exists embedding extensions.vector(768);

update public.user_memories
set normalized_text = lower(regexp_replace(trim(memory_text), '\s+', ' ', 'g'))
where normalized_text is null or normalized_text = '';

create unique index if not exists user_memories_unique_normalized
on public.user_memories (user_id, normalized_text)
where normalized_text is not null and normalized_text <> '';

create index if not exists user_memories_embedding_hnsw_idx
on public.user_memories
using hnsw (embedding extensions.vector_cosine_ops);

create index if not exists user_document_chunks_content_fts_idx
on public.user_document_chunks
using gin (to_tsvector('simple', coalesce(content, '')));

create or replace function public.match_user_memories(
  p_user_id uuid,
  p_query_embedding extensions.vector(768),
  p_match_count integer default 6,
  p_min_similarity double precision default 0.30
)
returns table (
  id uuid,
  memory_text text,
  category text,
  confidence double precision,
  source text,
  similarity double precision,
  updated_at timestamptz
)
language sql
stable
security definer
set search_path = public, extensions
as $$
  select
    m.id,
    m.memory_text,
    m.category,
    m.confidence,
    m.source,
    1 - (m.embedding <=> p_query_embedding) as similarity,
    m.updated_at
  from public.user_memories m
  where m.user_id = p_user_id
    and m.embedding is not null
    and m.confidence >= 0.85
    and 1 - (m.embedding <=> p_query_embedding) >= p_min_similarity
  order by m.embedding <=> p_query_embedding
  limit least(greatest(p_match_count, 1), 10);
$$;

revoke all on function public.match_user_memories(
  uuid, extensions.vector, integer, double precision
) from public, anon, authenticated;

grant execute on function public.match_user_memories(
  uuid, extensions.vector, integer, double precision
) to service_role;

create or replace function public.match_user_document_chunks_hybrid(
  p_user_id uuid,
  p_query_text text,
  p_query_embedding extensions.vector(768),
  p_match_count integer default 8,
  p_document_ids uuid[] default null
)
returns table (
  chunk_id bigint,
  document_id uuid,
  document_name text,
  page_number integer,
  content text,
  similarity double precision
)
language sql
stable
security definer
set search_path = public, extensions
as $$
  with scored as (
    select
      c.id as chunk_id,
      c.document_id,
      d.name as document_name,
      c.page_number,
      c.content,
      1 - (c.embedding <=> p_query_embedding) as vector_score,
      least(
        1.0,
        ts_rank_cd(
          to_tsvector('simple', coalesce(c.content, '')),
          websearch_to_tsquery('simple', coalesce(p_query_text, ''))
        ) * 4.0
      ) as keyword_score
    from public.user_document_chunks c
    join public.user_documents d on d.id = c.document_id
    where c.user_id = p_user_id
      and d.user_id = p_user_id
      and d.status = 'ready'
      and (
        p_document_ids is null
        or cardinality(p_document_ids) = 0
        or c.document_id = any(p_document_ids)
      )
  )
  select
    s.chunk_id,
    s.document_id,
    s.document_name,
    s.page_number,
    s.content,
    (0.72 * s.vector_score + 0.28 * s.keyword_score) as similarity
  from scored s
  where s.vector_score >= 0.24 or s.keyword_score > 0
  order by similarity desc
  limit least(greatest(p_match_count, 1), 15);
$$;

revoke all on function public.match_user_document_chunks_hybrid(
  uuid, text, extensions.vector, integer, uuid[]
) from public, anon, authenticated;

grant execute on function public.match_user_document_chunks_hybrid(
  uuid, text, extensions.vector, integer, uuid[]
) to service_role;
