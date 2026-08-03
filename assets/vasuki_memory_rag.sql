-- Vasuki AI: Personal Memory + Private Document RAG
-- Run this entire file once in Supabase SQL Editor.

create extension if not exists vector with schema extensions;

create table if not exists public.user_memory_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  enabled boolean not null default true,
  updated_at timestamptz not null default now()
);

create table if not exists public.user_memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  memory_text text not null check (char_length(memory_text) between 3 and 600),
  category text not null default 'preference',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists user_memories_unique_text
on public.user_memories (user_id, lower(memory_text));

create index if not exists user_memories_user_updated_idx
on public.user_memories (user_id, updated_at desc);

create table if not exists public.user_documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  mime_type text not null,
  size_bytes bigint not null default 0,
  status text not null default 'processing'
    check (status in ('processing', 'ready', 'failed')),
  chunk_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists user_documents_user_created_idx
on public.user_documents (user_id, created_at desc);

create table if not exists public.user_document_chunks (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  document_id uuid not null references public.user_documents(id) on delete cascade,
  chunk_index integer not null,
  page_number integer,
  content text not null,
  embedding extensions.vector(768) not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (document_id, chunk_index)
);

create index if not exists user_document_chunks_document_idx
on public.user_document_chunks (document_id, chunk_index);

create index if not exists user_document_chunks_user_idx
on public.user_document_chunks (user_id);

create index if not exists user_document_chunks_embedding_hnsw_idx
on public.user_document_chunks
using hnsw (embedding extensions.vector_cosine_ops);

alter table public.user_memory_settings enable row level security;
alter table public.user_memories enable row level security;
alter table public.user_documents enable row level security;
alter table public.user_document_chunks enable row level security;

drop policy if exists "Users manage own memory settings" on public.user_memory_settings;
create policy "Users manage own memory settings"
on public.user_memory_settings
for all
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users read own memories" on public.user_memories;
create policy "Users read own memories"
on public.user_memories
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users insert own memories" on public.user_memories;
create policy "Users insert own memories"
on public.user_memories
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists "Users update own memories" on public.user_memories;
create policy "Users update own memories"
on public.user_memories
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users delete own memories" on public.user_memories;
create policy "Users delete own memories"
on public.user_memories
for delete
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users read own documents" on public.user_documents;
create policy "Users read own documents"
on public.user_documents
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users insert own documents" on public.user_documents;
create policy "Users insert own documents"
on public.user_documents
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists "Users update own documents" on public.user_documents;
create policy "Users update own documents"
on public.user_documents
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users delete own documents" on public.user_documents;
create policy "Users delete own documents"
on public.user_documents
for delete
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users read own document chunks" on public.user_document_chunks;
create policy "Users read own document chunks"
on public.user_document_chunks
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users insert own document chunks" on public.user_document_chunks;
create policy "Users insert own document chunks"
on public.user_document_chunks
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists "Users delete own document chunks" on public.user_document_chunks;
create policy "Users delete own document chunks"
on public.user_document_chunks
for delete
to authenticated
using (auth.uid() = user_id);

create or replace function public.match_user_document_chunks(
  p_user_id uuid,
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
  select
    c.id as chunk_id,
    c.document_id,
    d.name as document_name,
    c.page_number,
    c.content,
    1 - (c.embedding <=> p_query_embedding) as similarity
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
    and 1 - (c.embedding <=> p_query_embedding) >= 0.30
  order by c.embedding <=> p_query_embedding
  limit least(greatest(p_match_count, 1), 15);
$$;

revoke all on function public.match_user_document_chunks(
  uuid, extensions.vector, integer, uuid[]
) from public, anon, authenticated;

grant execute on function public.match_user_document_chunks(
  uuid, extensions.vector, integer, uuid[]
) to service_role;
