-- 0005_profiles_display_name: additive expand for projects whose profiles
-- table predates this schema (e.g. starter templates with id/email only).
-- Safe re-run: add column if not exists; no data touched.

alter table public.profiles add column if not exists display_name text;
