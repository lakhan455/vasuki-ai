-- Vasuki AI V79
-- Add semantic vector retrieval to existing personal memory.
-- Safe additive migration.

create extension if not exists vector with schema extensions;

alter table public.user_memories
add column if not exists embedding extensions.vector(768);

create index if not exists user_memories_embedding_hnsw_idx
on public.user_memories
using hnsw (embedding extensions.vector_cosine_ops)
where embedding is not null;

create or replace function public.match_user_memories_v79(
    p_user_id uuid,
    p_query_embedding extensions.vector(768),
    p_match_count integer default 8
)
returns table (
    id uuid,
    memory_text text,
    category text,
    updated_at timestamptz,
    similarity double precision
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
        m.updated_at,
        1 - (m.embedding <=> p_query_embedding) as similarity
    from public.user_memories m
    where m.user_id = p_user_id
      and m.embedding is not null
    order by m.embedding <=> p_query_embedding
    limit least(
        greatest(p_match_count, 1),
        20
    );
$$;

revoke all on function public.match_user_memories_v79(
    uuid,
    extensions.vector,
    integer
) from public, anon, authenticated;

grant execute on function public.match_user_memories_v79(
    uuid,
    extensions.vector,
    integer
) to service_role;
