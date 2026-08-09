-- Vasuki AI V9 Phase 4
-- Background jobs, notifications, feature flags and A/B experiment events.

create table if not exists public.background_jobs_v9 (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null,
  status text not null default 'pending'
    check (status in ('pending','running','succeeded','failed','cancelled')),
  progress integer not null default 0 check (progress >= 0 and progress <= 100),
  input jsonb not null default '{}'::jsonb,
  output jsonb not null default '{}'::jsonb,
  error text,
  attempts integer not null default 0,
  worker_id text,
  locked_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists background_jobs_v9_user_created_idx
  on public.background_jobs_v9 (user_id, created_at desc);

create index if not exists background_jobs_v9_status_created_idx
  on public.background_jobs_v9 (status, created_at asc);

alter table public.background_jobs_v9 enable row level security;

drop policy if exists "Users read own V9 jobs" on public.background_jobs_v9;
create policy "Users read own V9 jobs"
on public.background_jobs_v9 for select to authenticated
using (auth.uid() = user_id);

create table if not exists public.notifications_v9 (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  body text not null default '',
  kind text not null default 'info',
  action_url text,
  metadata jsonb not null default '{}'::jsonb,
  read_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists notifications_v9_user_created_idx
  on public.notifications_v9 (user_id, created_at desc);

create index if not exists notifications_v9_unread_idx
  on public.notifications_v9 (user_id, read_at, created_at desc);

alter table public.notifications_v9 enable row level security;

drop policy if exists "Users read own V9 notifications" on public.notifications_v9;
create policy "Users read own V9 notifications"
on public.notifications_v9 for select to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users update own V9 notifications" on public.notifications_v9;
create policy "Users update own V9 notifications"
on public.notifications_v9 for update to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users delete own V9 notifications" on public.notifications_v9;
create policy "Users delete own V9 notifications"
on public.notifications_v9 for delete to authenticated
using (auth.uid() = user_id);

create table if not exists public.feature_flags_v9 (
  key text primary key,
  enabled boolean not null default true,
  rollout_percent integer not null default 100
    check (rollout_percent >= 0 and rollout_percent <= 100),
  variants jsonb not null default '{}'::jsonb,
  description text not null default '',
  updated_at timestamptz not null default now()
);

alter table public.feature_flags_v9 enable row level security;
-- No direct client policy. The owner API manages flags using the server credential.

create table if not exists public.experiment_events_v9 (
  id bigint generated always as identity primary key,
  user_id uuid references auth.users(id) on delete set null,
  experiment text not null,
  variant text not null,
  event text not null default 'exposure'
    check (event in ('exposure','conversion')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists experiment_events_v9_experiment_idx
  on public.experiment_events_v9 (experiment, variant, event, created_at desc);

create index if not exists experiment_events_v9_user_idx
  on public.experiment_events_v9 (user_id, created_at desc);

alter table public.experiment_events_v9 enable row level security;

drop policy if exists "Users read own V9 experiment events" on public.experiment_events_v9;
create policy "Users read own V9 experiment events"
on public.experiment_events_v9 for select to authenticated
using (auth.uid() = user_id);

create or replace function public.vasuki_v9_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists background_jobs_v9_touch on public.background_jobs_v9;
create trigger background_jobs_v9_touch
before update on public.background_jobs_v9
for each row execute function public.vasuki_v9_touch_updated_at();

drop trigger if exists notifications_v9_touch on public.notifications_v9;
create trigger notifications_v9_touch
before update on public.notifications_v9
for each row execute function public.vasuki_v9_touch_updated_at();

drop trigger if exists feature_flags_v9_touch on public.feature_flags_v9;
create trigger feature_flags_v9_touch
before update on public.feature_flags_v9
for each row execute function public.vasuki_v9_touch_updated_at();

create or replace function public.claim_vasuki_job_v9(p_worker_id text)
returns setof public.background_jobs_v9
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job public.background_jobs_v9%rowtype;
begin
  -- Recover jobs left running by a crashed/restarted web process.
  update public.background_jobs_v9
  set
    status = 'pending',
    progress = least(progress, 90),
    worker_id = null,
    locked_at = null,
    updated_at = now()
  where status = 'running'
    and locked_at < now() - interval '30 minutes'
    and attempts < 3;

  update public.background_jobs_v9
  set
    status = 'failed',
    progress = 100,
    error = coalesce(error, 'Job could not be recovered after repeated worker restarts.'),
    finished_at = now(),
    updated_at = now()
  where status = 'running'
    and locked_at < now() - interval '30 minutes'
    and attempts >= 3;

  select *
  into v_job
  from public.background_jobs_v9
  where status = 'pending'
  order by created_at asc
  for update skip locked
  limit 1;

  if not found then
    return;
  end if;

  update public.background_jobs_v9
  set
    status = 'running',
    progress = greatest(progress, 5),
    worker_id = left(coalesce(p_worker_id, 'vasuki-worker'), 160),
    locked_at = now(),
    attempts = attempts + 1,
    updated_at = now()
  where id = v_job.id
  returning * into v_job;

  return next v_job;
end;
$$;

revoke all on function public.claim_vasuki_job_v9(text) from public;
grant execute on function public.claim_vasuki_job_v9(text) to service_role;
