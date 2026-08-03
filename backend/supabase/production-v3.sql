-- Vasuki AI Pro + Puter + Razorpay
-- Run this complete file once in Supabase Dashboard > SQL Editor.

create table if not exists public.user_plans (
  user_id uuid primary key references auth.users(id) on delete cascade,
  plan text not null default 'free' check (plan in ('free', 'pro')),
  pro_expires_at timestamptz,
  source text,
  last_payment_id text,
  last_order_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists user_plans_expiry_idx
on public.user_plans (pro_expires_at desc);

alter table public.user_plans enable row level security;

drop policy if exists "Users read own plan" on public.user_plans;
create policy "Users read own plan"
on public.user_plans for select to authenticated
using (auth.uid() = user_id);

create table if not exists public.payment_orders (
  order_id text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  amount_paise integer not null check (amount_paise > 0),
  currency text not null default 'INR',
  status text not null default 'created'
    check (status in ('created', 'paid', 'failed', 'refunded')),
  payment_id text,
  signature text,
  created_at timestamptz not null default now(),
  paid_at timestamptz
);

create index if not exists payment_orders_user_created_idx
on public.payment_orders (user_id, created_at desc);

create unique index if not exists payment_orders_payment_id_unique
on public.payment_orders (payment_id) where payment_id is not null;

alter table public.payment_orders enable row level security;

drop policy if exists "Users read own payment orders" on public.payment_orders;
create policy "Users read own payment orders"
on public.payment_orders for select to authenticated
using (auth.uid() = user_id);

-- No client write policies. Only the backend service credential activates Pro.
