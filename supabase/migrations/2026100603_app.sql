-- 0003_app: billing ledger, notifications, feedback, admin audit.
-- billing_events + admin_events are service-role only (no user policies).

create table if not exists public.billing_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null default 'dodo',
  event_id text not null unique,
  type text not null,
  user_id uuid references public.profiles (id) on delete set null,
  payload jsonb,
  processed_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  kind text not null,
  title text not null,
  body text,
  read_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists notifications_user_idx on public.notifications (user_id, created_at desc);

create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  job_id uuid references public.conversion_jobs (id) on delete set null,
  rating boolean,
  category text,
  comment text,
  created_at timestamptz not null default now()
);

create table if not exists public.admin_events (
  id uuid primary key default gen_random_uuid(),
  actor text not null,
  action text not null,
  target text,
  detail jsonb,
  created_at timestamptz not null default now()
);

alter table public.billing_events enable row level security;
alter table public.notifications enable row level security;
alter table public.feedback enable row level security;
alter table public.admin_events enable row level security;

drop policy if exists "own notifications" on public.notifications;
create policy "own notifications" on public.notifications
  for select using (auth.uid() = user_id);

drop policy if exists "own feedback" on public.feedback;
create policy "own feedback" on public.feedback
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
