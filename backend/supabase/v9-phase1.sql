-- Vasuki AI V9 Phase 1 memory policy migration
alter table public.user_memories
  add column if not exists memory_type text,
  add column if not exists subject_key text,
  add column if not exists status text not null default 'active',
  add column if not exists superseded_by uuid,
  add column if not exists expires_at timestamptz;

create index if not exists user_memories_subject_active_idx
on public.user_memories (user_id, subject_key, status);

create index if not exists user_memories_expiry_idx
on public.user_memories (expires_at) where expires_at is not null;

alter table public.user_memories drop constraint if exists user_memories_status_check;
alter table public.user_memories
  add constraint user_memories_status_check check (status in ('active','superseded','expired'));
