-- Run this once in Supabase > SQL Editor only when chat deletion
-- says that the row-level security policy blocks the delete.
alter table public.user_chats enable row level security;

drop policy if exists "Users can delete own chats"
on public.user_chats;

create policy "Users can delete own chats"
on public.user_chats
for delete
to authenticated
using (auth.uid() = user_id);
