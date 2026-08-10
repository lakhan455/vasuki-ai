-- Vasuki AI V9 Phase 6
create table if not exists public.audit_logs_v9 (
  id bigint generated always as identity primary key,
  actor_user_id uuid references auth.users(id) on delete set null,
  action text not null, outcome text not null default 'success', target_type text, target_id text,
  request_id text, ip_hash text, user_agent_hash text, metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists audit_logs_v9_created_idx on public.audit_logs_v9 (created_at desc);
create index if not exists audit_logs_v9_actor_idx on public.audit_logs_v9 (actor_user_id, created_at desc);
create index if not exists audit_logs_v9_action_idx on public.audit_logs_v9 (action, created_at desc);
alter table public.audit_logs_v9 enable row level security;

create table if not exists public.secret_rotation_events_v9 (
  id uuid primary key default gen_random_uuid(), secret_name text not null, previous_fingerprint text,
  current_fingerprint text not null, rotated_by uuid references auth.users(id) on delete set null,
  note text, created_at timestamptz not null default now()
);
create index if not exists secret_rotation_events_v9_created_idx on public.secret_rotation_events_v9 (created_at desc);
alter table public.secret_rotation_events_v9 enable row level security;

create table if not exists public.app_backups_v9 (
  id uuid primary key default gen_random_uuid(), created_by uuid references auth.users(id) on delete set null,
  note text, schema_version text not null, sha256 text not null,
  compressed_bytes bigint not null check (compressed_bytes >= 0), table_counts jsonb not null default '{}'::jsonb,
  warnings jsonb not null default '[]'::jsonb, payload_b64 text not null, created_at timestamptz not null default now()
);
create index if not exists app_backups_v9_created_idx on public.app_backups_v9 (created_at desc);
alter table public.app_backups_v9 enable row level security;

create table if not exists public.eval_runs_v9 (
  id uuid primary key default gen_random_uuid(), version text not null,
  questions integer not null default 0 check (questions >= 0),
  overall_score double precision not null check (overall_score >= 0 and overall_score <= 100),
  average_latency_ms double precision not null default 0 check (average_latency_ms >= 0),
  category_scores jsonb not null default '{}'::jsonb, recorded_by uuid references auth.users(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
create index if not exists eval_runs_v9_created_idx on public.eval_runs_v9 (created_at desc);
alter table public.eval_runs_v9 enable row level security;

create table if not exists public.release_health_v9 (
  id bigint generated always as identity primary key, status text not null, checks jsonb not null default '[]'::jsonb,
  security_score integer, eval_score double precision, created_at timestamptz not null default now()
);
create index if not exists release_health_v9_created_idx on public.release_health_v9 (created_at desc);
alter table public.release_health_v9 enable row level security;

alter table public.system_error_events
  add column if not exists severity text not null default 'error',
  add column if not exists fingerprint text,
  add column if not exists resolved_at timestamptz,
  add column if not exists resolved_by uuid references auth.users(id) on delete set null;
create index if not exists system_error_events_fingerprint_idx on public.system_error_events (fingerprint, created_at desc);
create index if not exists system_error_events_unresolved_idx on public.system_error_events (created_at desc) where resolved_at is null;
