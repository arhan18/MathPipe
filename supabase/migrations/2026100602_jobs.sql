-- 0002_jobs: conversion jobs, artifacts, pages, verification, event log.

create table if not exists public.conversion_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  source_file_id text not null,
  source_artifact_key text,
  mode text not null default 'standard' check (mode in ('standard', 'verified')),
  page_range text,
  state text not null default 'queued' check (state in (
    'uploaded', 'validating', 'queued', 'analyzing', 'processing',
    'reconstructing', 'verifying', 'repairing', 'finalizing',
    'completed', 'completed_with_warnings', 'failed', 'cancelled', 'expired'
  )),
  error_code text,
  retryable boolean not null default false,
  warning_count integer not null default 0,
  artifact_id text,
  sequence integer not null default 0,
  idempotency_key text unique,
  plan_id text references public.plans (id),
  cost_estimate_cents integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists conversion_jobs_user_idx on public.conversion_jobs (user_id, created_at desc);
create index if not exists conversion_jobs_state_idx on public.conversion_jobs (state, updated_at);

create table if not exists public.conversion_artifacts (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.conversion_jobs (id) on delete cascade,
  user_id uuid not null references public.profiles (id) on delete cascade,
  kind text not null check (kind in ('source', 'output', 'intermediate', 'verification')),
  storage_key text not null,
  content_type text,
  size_bytes bigint,
  checksum text,
  expires_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists conversion_artifacts_expiry_idx
  on public.conversion_artifacts (expires_at) where deleted_at is null;

create table if not exists public.conversion_pages (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.conversion_jobs (id) on delete cascade,
  page_number integer not null,
  state text not null default 'queued',
  confidence numeric,
  error_code text,
  created_at timestamptz not null default now(),
  unique (job_id, page_number)
);

create table if not exists public.verification_runs (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.conversion_jobs (id) on delete cascade,
  page_number integer,
  provider text,
  model text,
  status text not null default 'pending'
    check (status in ('pending', 'passed', 'repaired', 'escalated', 'failed')),
  cost_estimate_cents integer not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists public.verification_issues (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references public.verification_runs (id) on delete set null,
  job_id uuid not null references public.conversion_jobs (id) on delete cascade,
  page_number integer,
  category text,
  status text not null default 'new'
    check (status in ('new', 'investigating', 'fixed', 'wont_fix', 'duplicate')),
  detail jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.job_events (
  job_id uuid not null references public.conversion_jobs (id) on delete cascade,
  sequence integer not null,
  type text not null,
  state text not null,
  stage text not null,
  payload jsonb,
  created_at timestamptz not null default now(),
  primary key (job_id, sequence)
);

-- RLS: owners read their jobs; writes go through the service role.
alter table public.conversion_jobs enable row level security;
alter table public.conversion_artifacts enable row level security;
alter table public.conversion_pages enable row level security;
alter table public.verification_runs enable row level security;
alter table public.verification_issues enable row level security;
alter table public.job_events enable row level security;

drop policy if exists "own jobs" on public.conversion_jobs;
create policy "own jobs" on public.conversion_jobs
  for select using (auth.uid() = user_id);

drop policy if exists "own artifacts" on public.conversion_artifacts;
create policy "own artifacts" on public.conversion_artifacts
  for select using (auth.uid() = user_id);

drop policy if exists "own pages" on public.conversion_pages;
create policy "own pages" on public.conversion_pages
  for select using (
    auth.uid() = (select user_id from public.conversion_jobs where id = job_id)
  );

drop policy if exists "own verification runs" on public.verification_runs;
create policy "own verification runs" on public.verification_runs
  for select using (
    auth.uid() = (select user_id from public.conversion_jobs where id = job_id)
  );

drop policy if exists "own verification issues" on public.verification_issues;
create policy "own verification issues" on public.verification_issues
  for select using (
    auth.uid() = (select user_id from public.conversion_jobs where id = job_id)
  );

drop policy if exists "own job events" on public.job_events;
create policy "own job events" on public.job_events
  for select using (
    auth.uid() = (select user_id from public.conversion_jobs where id = job_id)
  );
