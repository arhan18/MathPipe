-- 0004_seed: plan quotas (§25, §22.1). Quotas are config rows, never code.
-- Re-run safe: upserts by plan id.

insert into public.plans (id, conversion_pages, verified_pages, max_file_mb, max_pages_per_job, max_concurrent_jobs)
values
  ('free', 10, 0, 25, 25, 1),
  ('pro', 500, 50, 50, 150, 3),
  ('power', 1500, 150, 100, 500, 5),
  ('business', 5000, 500, 250, 1000, 25)
on conflict (id) do update set
  conversion_pages = excluded.conversion_pages,
  verified_pages = excluded.verified_pages,
  max_file_mb = excluded.max_file_mb,
  max_pages_per_job = excluded.max_pages_per_job,
  max_concurrent_jobs = excluded.max_concurrent_jobs;
