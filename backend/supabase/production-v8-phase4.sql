-- Vasuki AI V8 Phase 4 Start

create extension if not exists vector with schema extensions;

create table if not exists public.project_memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  memory_text text not null,
  normalized_text text not null,
  source text not null default 'manual',
  confidence real not null default 1.0 check (confidence >= 0 and confidence <= 1),
  embedding extensions.vector(768),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (project_id, normalized_text)
);

create index if not exists project_memories_user_project_updated_idx
on public.project_memories (user_id, project_id, updated_at desc);

alter table public.project_memories enable row level security;

drop policy if exists "Users read own project memories" on public.project_memories;
create policy "Users read own project memories"
on public.project_memories for select to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users insert own project memories" on public.project_memories;
create policy "Users insert own project memories"
on public.project_memories for insert to authenticated
with check (
  auth.uid() = user_id
  and exists (
    select 1 from public.projects p
    where p.id = project_id and p.user_id = auth.uid()
  )
);

drop policy if exists "Users update own project memories" on public.project_memories;
create policy "Users update own project memories"
on public.project_memories for update to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users delete own project memories" on public.project_memories;
create policy "Users delete own project memories"
on public.project_memories for delete to authenticated
using (auth.uid() = user_id);

alter table public.user_chats
  add column if not exists project_id uuid references public.projects(id) on delete set null;

create index if not exists user_chats_user_project_updated_idx
on public.user_chats (user_id, project_id, updated_at desc);

create or replace function public.match_project_memories(
  p_user_id uuid,
  p_project_id uuid,
  p_query_embedding extensions.vector(768),
  p_match_count integer default 8,
  p_min_similarity real default 0.28
)
returns table (
  id uuid,
  project_id uuid,
  memory_text text,
  normalized_text text,
  source text,
  confidence real,
  similarity real,
  created_at timestamptz,
  updated_at timestamptz
)
language sql
stable
security invoker
set search_path = public, extensions
as $$
  select
    pm.id,
    pm.project_id,
    pm.memory_text,
    pm.normalized_text,
    pm.source,
    pm.confidence,
    (1 - (pm.embedding <=> p_query_embedding))::real as similarity,
    pm.created_at,
    pm.updated_at
  from public.project_memories pm
  where pm.user_id = p_user_id
    and pm.project_id = p_project_id
    and pm.embedding is not null
    and (1 - (pm.embedding <=> p_query_embedding)) >= p_min_similarity
  order by pm.embedding <=> p_query_embedding
  limit greatest(1, least(p_match_count, 12));
$$;

grant execute on function public.match_project_memories(
  uuid, uuid, extensions.vector, integer, real
) to authenticated, service_role;

