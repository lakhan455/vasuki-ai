-- Vasuki AI V9 Phase 2 — Project Knowledge Base V2

create table if not exists public.project_files_v9 (
  id uuid primary key,
  user_id uuid not null,
  project_id uuid not null,
  path text not null,
  name text not null,
  mime_type text,
  size_bytes bigint not null default 0,
  language text,
  content_text text not null default '',
  content_sha256 text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, project_id, path)
);

create index if not exists project_files_v9_project_idx
  on public.project_files_v9 (user_id, project_id, path);

create index if not exists project_files_v9_updated_idx
  on public.project_files_v9 (user_id, project_id, updated_at desc);

create table if not exists public.project_file_versions_v9 (
  id uuid primary key,
  user_id uuid not null,
  project_id uuid not null,
  path text not null,
  operation text not null,
  previous_content text not null default '',
  previous_sha256 text,
  created_at timestamptz not null default now(),
  constraint project_file_versions_v9_operation_check
    check (operation in ('create','update','delete'))
);

create index if not exists project_file_versions_v9_project_idx
  on public.project_file_versions_v9 (user_id, project_id, path, created_at desc);

alter table public.project_files_v9 enable row level security;
alter table public.project_file_versions_v9 enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname='public' and tablename='project_files_v9'
      and policyname='project_files_v9_owner_all'
  ) then
    create policy project_files_v9_owner_all
      on public.project_files_v9
      for all
      using (auth.uid() = user_id)
      with check (auth.uid() = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname='public' and tablename='project_file_versions_v9'
      and policyname='project_file_versions_v9_owner_all'
  ) then
    create policy project_file_versions_v9_owner_all
      on public.project_file_versions_v9
      for all
      using (auth.uid() = user_id)
      with check (auth.uid() = user_id);
  end if;
end $$;
