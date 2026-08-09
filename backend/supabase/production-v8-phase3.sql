-- Vasuki AI V8 Phase 3 Start
-- Projects/workspaces, feedback and branching foundation

create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  description text,
  instructions text,
  color text not null default '#8b5cf6',
  archived boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists projects_user_updated_idx
on public.projects (user_id, updated_at desc);

alter table public.projects enable row level security;

drop policy if exists "Users read own projects" on public.projects;
create policy "Users read own projects"
on public.projects for select to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users insert own projects" on public.projects;
create policy "Users insert own projects"
on public.projects for insert to authenticated
with check (auth.uid() = user_id);

drop policy if exists "Users update own projects" on public.projects;
create policy "Users update own projects"
on public.projects for update to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users delete own projects" on public.projects;
create policy "Users delete own projects"
on public.projects for delete to authenticated
using (auth.uid() = user_id);

create table if not exists public.response_feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  message_id text,
  rating text not null,
  category text not null default 'other',
  comment text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists response_feedback_user_created_idx
on public.response_feedback (user_id, created_at desc);

alter table public.response_feedback enable row level security;

drop policy if exists "Users read own feedback" on public.response_feedback;
create policy "Users read own feedback"
on public.response_feedback for select to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users insert own feedback" on public.response_feedback;
create policy "Users insert own feedback"
on public.response_feedback for insert to authenticated
with check (auth.uid() = user_id);

create table if not exists public.conversation_branches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  conversation_id text not null,
  source_message_id text,
  original_prompt text not null,
  edited_prompt text not null,
  note text,
  created_at timestamptz not null default now()
);

create index if not exists conversation_branches_user_conv_idx
on public.conversation_branches (user_id, conversation_id, created_at desc);

alter table public.conversation_branches enable row level security;

drop policy if exists "Users read own branches" on public.conversation_branches;
create policy "Users read own branches"
on public.conversation_branches for select to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users insert own branches" on public.conversation_branches;
create policy "Users insert own branches"
on public.conversation_branches for insert to authenticated
with check (auth.uid() = user_id);
