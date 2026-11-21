import { isDbConfigured, createServiceClient } from "@mathpipe/db";
import type { JobState } from "@mathpipe/jobs";
import { AdminShell } from "../gate";
import { RequeueButton } from "@/components/admin/RequeueButton";

export const metadata = { title: "Admin · Jobs" };
export const dynamic = "force-dynamic";

interface JobRow { id: string; state: string; mode: string; updated: string; error_code: string | null; warning_count: number }

export default async function AdminJobsPage() {
  let rows: JobRow[] = [];
  let live = false;
  if (isDbConfigured()) {
    live = true;
    const db = createServiceClient();
    const { data } = await db
      .from("conversion_jobs")
      .select("id,state,mode,updated_at,error_code,warning_count")
      .order("updated_at", { ascending: false })
      .limit(50);
    rows = (data ?? []).map((r) => ({
      id: r.id as string,
      state: r.state as JobState,
      mode: r.mode as string,
      updated: r.updated_at as string,
      error_code: (r.error_code as string) ?? null,
      warning_count: (r.warning_count as number) ?? 0,
    }));
  }

  const stuckSet = new Set(["analyzing", "processing", "reconstructing", "finalizing"]);
  const stuck = rows.filter((r) => stuckSet.has(r.state));

  return (
    <AdminShell>
      <div className="mx-auto max-w-6xl px-6 py-16">
        <h1 className="font-display text-4xl">Jobs</h1>
        <p className="mt-2 text-neutral-400">
          {live ? "Latest 50 conversions across all users." : "Database not connected — live job inspection activates with Supabase keys."}
        </p>
        <div className="mt-8 overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="text-neutral-400 border-b border-white/10">
              <tr>
                <th className="px-4 py-3 font-medium">Job</th>
                <th className="px-4 py-3 font-medium">State</th>
                <th className="px-4 py-3 font-medium">Mode</th>
                <th className="px-4 py-3 font-medium">Error / Warnings</th>
                <th className="px-4 py-3 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-neutral-500">No jobs to show.</td></tr>
              )}
              {rows.map((r) => {
                const isStuck = stuckSet.has(r.state);
                return (
                <tr key={r.id} className="border-b border-white/5 last:border-0">
                  <td className="px-4 py-3 font-mono text-xs">{r.id.slice(0, 12)}…</td>
                  <td className="px-4 py-3">{r.state}</td>
                  <td className="px-4 py-3">{r.mode}</td>
                  <td className="px-4 py-3">{r.error_code ?? r.warning_count > 0 ? `${r.error_code ?? ""} ${r.warning_count > 0 ? `(${r.warning_count} warnings)` : ""}` : "—"}{isStuck && <RequeueButton jobId={r.id} />}</td>
                  <td className="px-4 py-3 text-neutral-400">{r.updated}</td>
                </tr>
              );
              })}
            </tbody>
          </table>
        </div>

        {stuck.length > 0 && (
          <p className="mt-4 text-sm text-amber-400">{stuck.length} job{stuck.length > 1 ? "s" : ""} in working state — the poller requeues them automatically if idle 30+ min.</p>
        )}
      </div>
    </AdminShell>
  );
}
