import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import { redirect } from "next/navigation";
import type { User } from "@supabase/supabase-js";

/**
 * Server-side session guard for dashboard pages. Redirects to /login when no
 * user is present, so dashboard routes never render for anonymous visitors.
 */
export async function requireUser(
  nextPath: string,
): Promise<{ supabase: ReturnType<typeof createServerClient>; user: User }> {
  const jar = await cookies();
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => jar.getAll(), setAll: () => {} } },
  );
  const { data } = await supabase.auth.getUser();
  if (!data.user) redirect(`/login?next=${encodeURIComponent(nextPath)}`);
  return { supabase, user: data.user };
}
