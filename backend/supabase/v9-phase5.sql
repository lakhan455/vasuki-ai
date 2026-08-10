-- Vasuki AI V9 Phase 5
-- Push subscriptions + storage quota RPC.

create table if not exists public.push_subscriptions_v9 (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  endpoint_hash text not null,
  endpoint text not null,
  subscription jsonb not null default '{}'::jsonb,
  user_agent text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, endpoint_hash)
);

create index if not exists push_subscriptions_v9_user_idx
  on public.push_subscriptions_v9 (user_id, updated_at desc);

alter table public.push_subscriptions_v9 enable row level security;

drop policy if exists "Users read own V9 push subscriptions" on public.push_subscriptions_v9;
create policy "Users read own V9 push subscriptions"
on public.push_subscriptions_v9 for select to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users delete own V9 push subscriptions" on public.push_subscriptions_v9;
create policy "Users delete own V9 push subscriptions"
on public.push_subscriptions_v9 for delete to authenticated
using (auth.uid() = user_id);

drop trigger if exists push_subscriptions_v9_touch on public.push_subscriptions_v9;
create trigger push_subscriptions_v9_touch
before update on public.push_subscriptions_v9
for each row execute function public.vasuki_v9_touch_updated_at();

create or replace function public.storage_usage_v9(p_user_id uuid)
returns table (
  artifact_bytes bigint,
  document_bytes bigint,
  project_bytes bigint
)
language sql
stable
security definer
set search_path = public
as $$
  select
    coalesce((
      select sum(coalesce(size_bytes, 0))
      from public.generated_artifacts
      where user_id = p_user_id
    ), 0)::bigint,
    coalesce((
      select sum(coalesce(size_bytes, 0))
      from public.user_documents
      where user_id = p_user_id
    ), 0)::bigint,
    coalesce((
      select sum(coalesce(size_bytes, 0))
      from public.project_files_v9
      where user_id = p_user_id
    ), 0)::bigint;
$$;

revoke all on function public.storage_usage_v9(uuid)
from public, anon, authenticated;
grant execute on function public.storage_usage_v9(uuid)
to service_role;
