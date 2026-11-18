-- 0005_profile_trigger: create a profiles row for every new auth user.
--
-- Root cause of the first e2e failure: signups created auth.users rows but no
-- profiles row, so every conversion_jobs insert died on the FK. The web app
-- also bootstraps defensively via ensureProfile() (@mathpipe/db); this trigger
-- is the canonical path for environments provisioned after this file lands.
-- APPLY WITH: supabase CLI access (pending — no CLI credentials in this env).

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, split_part(new.email, '@', 1))
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
