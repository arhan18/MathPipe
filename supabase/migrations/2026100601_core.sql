-- 0001_core: identity, plans, subscriptions, usage ledger (§23–§25).
-- Append-only usage_events: no UPDATE/DELETE policies by design.

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now()
);

create table if not exists public.plans (
  id text primary key,
  conversion_pages integer not null,
  verified_pages integer not null,
  max_file_mb integer not null,
  max_pages_per_job integer not null,
  max_concurrent_jobs integer not null
);

create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  plan_id text not null references public.plans (id),
  status text not null default 'active'
    check (status in ('active', 'cancelled', 'past_due', 'trialing')),
  dodo_customer_id text,
  dodo_subscription_id text,
  current_period_start timestamptz,
  current_period_end timestamptz,
  created_at timestamptz not null default now()
);
create unique index if not exists subscriptions_one_active_per_user
  on public.subscriptions (user_id) where status = 'active';

create table if not exists public.usage_periods (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  plan_id text not null references public.plans (id),
  started_at timestamptz not null default now(),
  ends_at timestamptz not null,
  created_at timestamptz not null default now()
);
create index if not exists usage_periods_user_idx on public.usage_periods (user_id, ends_at desc);

create table if not exists public.usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  period_id uuid references public.usage_periods (id),
  kind text not null check (kind in (
    'conversion_page_consumed',
    'verification_page_consumed',
    'extra_credit_consumed',
    'credit_granted'
  )),
  quantity integer not null default 1,
  job_id uuid,
  created_at timestamptz not null default now()
);
create index if not exists usage_events_user_idx on public.usage_events (user_id, created_at desc);

-- RLS
alter table public.profiles enable row level security;
alter table public.plans enable row level security;
alter table public.subscriptions enable row level security;
alter table public.usage_periods enable row level security;
alter table public.usage_events enable row level security;

drop policy if exists "own profile" on public.profiles;
create policy "own profile" on public.profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists "plans readable" on public.plans;
create policy "plans readable" on public.plans for select using (true);

drop policy if exists "own subscriptions" on public.subscriptions;
create policy "own subscriptions" on public.subscriptions
  for select using (auth.uid() = user_id);

drop policy if exists "own periods" on public.usage_periods;
create policy "own periods" on public.usage_periods
  for select using (auth.uid() = user_id);

drop policy if exists "own usage" on public.usage_events;
create policy "own usage" on public.usage_events
  for select using (auth.uid() = user_id);
-- No INSERT/UPDATE/DELETE policies: metering writes use the service role only.
