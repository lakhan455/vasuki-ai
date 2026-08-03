-- Vasuki Pro image quota reserve + refund
-- Run this complete file once in Supabase Dashboard > SQL Editor.

create table if not exists public.user_daily_puter_images (
  user_id uuid not null references auth.users(id) on delete cascade,
  usage_date date not null,
  image_count integer not null default 0 check (image_count >= 0),
  updated_at timestamptz not null default now(),
  primary key (user_id, usage_date)
);

alter table public.user_daily_puter_images enable row level security;

create or replace function public.consume_puter_image_quota(
  p_user_id uuid,
  p_daily_limit integer
)
returns table (
  allowed boolean,
  image_count integer,
  daily_remaining integer
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_usage_date date := (now() at time zone 'Asia/Kolkata')::date;
  v_count integer;
begin
  if p_user_id is null or p_daily_limit < 1 then
    raise exception 'Invalid quota arguments';
  end if;

  insert into public.user_daily_puter_images (
    user_id,
    usage_date,
    image_count,
    updated_at
  )
  values (
    p_user_id,
    v_usage_date,
    0,
    now()
  )
  on conflict (user_id, usage_date) do nothing;

  select u.image_count
  into v_count
  from public.user_daily_puter_images u
  where u.user_id = p_user_id
    and u.usage_date = v_usage_date
  for update;

  if v_count >= p_daily_limit then
    return query select false, v_count, 0;
    return;
  end if;

  v_count := v_count + 1;

  update public.user_daily_puter_images
  set image_count = v_count,
      updated_at = now()
  where user_id = p_user_id
    and usage_date = v_usage_date;

  return query
  select true, v_count, greatest(0, p_daily_limit - v_count);
end;
$$;

create or replace function public.release_puter_image_quota(
  p_user_id uuid,
  p_daily_limit integer
)
returns table (
  allowed boolean,
  image_count integer,
  daily_remaining integer
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_usage_date date := (now() at time zone 'Asia/Kolkata')::date;
  v_count integer;
begin
  if p_user_id is null or p_daily_limit < 1 then
    raise exception 'Invalid quota arguments';
  end if;

  insert into public.user_daily_puter_images (
    user_id,
    usage_date,
    image_count,
    updated_at
  )
  values (
    p_user_id,
    v_usage_date,
    0,
    now()
  )
  on conflict (user_id, usage_date) do nothing;

  update public.user_daily_puter_images
  set image_count = greatest(0, image_count - 1),
      updated_at = now()
  where user_id = p_user_id
    and usage_date = v_usage_date
  returning user_daily_puter_images.image_count
  into v_count;

  return query
  select true, v_count, greatest(0, p_daily_limit - v_count);
end;
$$;

revoke all on function public.consume_puter_image_quota(uuid, integer)
from public, anon, authenticated;

revoke all on function public.release_puter_image_quota(uuid, integer)
from public, anon, authenticated;

grant execute on function public.consume_puter_image_quota(uuid, integer)
to service_role;

grant execute on function public.release_puter_image_quota(uuid, integer)
to service_role;
