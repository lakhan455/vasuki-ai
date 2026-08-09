-- Vasuki AI V8 Phase 2 Core
-- Analytics + generated artifact metadata + private storage bucket

create table if not exists public.usage_events (
  id bigint generated always as identity primary key,
  user_id uuid references auth.users(id) on delete set null,
  feature text not null,
  provider text,
  status text not null default 'ok',
  latency_ms double precision,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists usage_events_created_idx
on public.usage_events (created_at desc);

create index if not exists usage_events_user_created_idx
on public.usage_events (user_id, created_at desc);

create index if not exists usage_events_feature_created_idx
on public.usage_events (feature, created_at desc);

alter table public.usage_events enable row level security;

drop policy if exists "Users read own usage events" on public.usage_events;
create policy "Users read own usage events"
on public.usage_events for select to authenticated
using (auth.uid() = user_id);

create table if not exists public.generated_artifacts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  artifact_type text not null default 'file',
  mime_type text not null,
  storage_path text,
  external_url text,
  size_bytes bigint,
  prompt text,
  provider text,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '30 days')
);

create index if not exists generated_artifacts_user_created_idx
on public.generated_artifacts (user_id, created_at desc);

create index if not exists generated_artifacts_expiry_idx
on public.generated_artifacts (expires_at);

alter table public.generated_artifacts enable row level security;

drop policy if exists "Users read own generated artifacts" on public.generated_artifacts;
create policy "Users read own generated artifacts"
on public.generated_artifacts for select to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users delete own generated artifacts" on public.generated_artifacts;
create policy "Users delete own generated artifacts"
on public.generated_artifacts for delete to authenticated
using (auth.uid() = user_id);

insert into storage.buckets (id, name, public, file_size_limit)
values ('vasuki-artifacts', 'vasuki-artifacts', false, 52428800)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit;

drop policy if exists "Users read own Vasuki artifacts" on storage.objects;
create policy "Users read own Vasuki artifacts"
on storage.objects for select to authenticated
using (
  bucket_id = 'vasuki-artifacts'
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists "Users delete own Vasuki artifacts" on storage.objects;
create policy "Users delete own Vasuki artifacts"
on storage.objects for delete to authenticated
using (
  bucket_id = 'vasuki-artifacts'
  and (storage.foldername(name))[1] = auth.uid()::text
);
