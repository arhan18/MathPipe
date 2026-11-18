import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import { redirect } from "next/navigation";

/**
 * Admin gate: authenticated session + email on ADMIN_EMAILS.
 * Everything else — including signed-in non-admins — gets a 403.
 * Admin pages never render user file contents, only metadata.
 */
export async function requireAdmin(): Promise<{ email: string } | { denied: string }> {
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) {
    return { denied: "Admin is disabled until authentication is configured." };
  }
  const jar = await cookies();
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    { cookies: { getAll: () => jar.getAll(), setAll: () => {} } },
  );
  const { data } = await supabase.auth.getUser();
  const email = data.user?.email ?? "";
  const allowlist = (process.env.ADMIN_EMAILS ?? "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  if (!email || !allowlist.includes(email.toLowerCase())) {
    return { denied: "Forbidden." };
  }
  return { email };
}

export async function AdminShell({ children }: { children: React.ReactNode }) {
  const check = await requireAdmin();
  if ("denied" in check) redirect(`/login?next=/admin&reason=${encodeURIComponent(check.denied)}`);
  return <>{children}</>;
}
