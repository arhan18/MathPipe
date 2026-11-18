import { isDbConfigured, createServiceClient } from "@mathpipe/db";
import type { JobState } from "@mathpipe/jobs";
import { AdminShell } from "../gate";

export const metadata = { title: "Admin · Jobs" };
export const dynamic = "force-dynamic";

export default async function AdminJobsPage() {
  let rows: Array<{ id: string; state: string; mode: string; updated: string }> = [];
  let live = false;
  if (isDbConfigured()) {
    live = true;
    const db = createServiceClient();
    const { data } = await db
      .from("conversion_jobs")
      .select("id,state,mode,updated_at")
      .order("updated_at", { ascending: false })
      .limit(50);
    rows = (data ?? []).map((r) => ({
      id: r.id as string,
      state: r.state as JobState,
      mode: r.mode as string,
      updated: r.updated_at as string,
    }));
  }

  return (
    <AdminShell>
      <div className="mx-auto max-w-6xl px-6 py-16">
        <h1 className="font-display text-4xl">Jobs</h1>
        <p className="mt-2 text-neutral-400">
          {live ? "Latest 50 conversions across all users." : "Database not connected — live job inspection activates with Supabase keys."}
        </p>
        <div className="mt-8 overflow-x-auto rounded-2xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-neutral-400">
                <th className="px-4 py-3 font-medium">Job</th>
                <th className="px-4 py-3 font-medium">State</th>
                <th className="px-4 py-3 font-medium">Mode</th>
                <th className="px-4 py-3 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-neutral-500">No jobs to show.</td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-white/5 last:border-0">
                  <td className="px-4 py-3 font-mono text-xs">{r.id.slice(0, 12)}…</td>
                  <td className="px-4 py-3">{r.state}</td>
                  <td className="px-4 py-3">{r.mode}</td>
                  <td className="px-4 py-3 text-neutral-400">{r.updated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AdminShell>
  );
}
