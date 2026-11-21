import { isDbConfigured, createServiceClient } from "@mathpipe/db";
import { AdminShell } from "../gate";

export const metadata = { title: "Admin · Usage" };
export const dynamic = "force-dynamic";

interface UsageRow { id: string; email: string | null; jobs_total: number; jobs_failed: number; }

export default async function AdminUsagePage() {
  const rows: UsageRow[] = [];
  const states: Array<{ state: string; count: number }> = [];
  if (isDbConfigured()) {
    const db = createServiceClient();
    const { data: jobs } = await db.from("conversion_jobs").select("id,state,user_id").order("created_at", { ascending: false }).limit(5000);
    const byUser = new Map<string, { total: number; failed: number }>();
    for (const j of (jobs ?? []) as Array<{ state: string; user_id: string }>) {
      const acc = byUser.get(j.user_id) ?? { total: 0, failed: 0 };
      acc.total += 1;
      if (j.state === "failed") acc.failed += 1;
      byUser.set(j.user_id, acc);
    }
    const { data: profiles } = await db.from("profiles").select("id,display_name");
    const nameByProfile = new Map((profiles ?? []).map((p: any) => [p.id, p.display_name as string | null]));
    for (const [uid, acc] of [...byUser].sort((a, b) => b[1].total - a[1].total).slice(0, 20)) {
      rows.push({ id: uid, email: (nameByProfile.get(uid) as string | null) ?? null, jobs_total: acc.total, jobs_failed: acc.failed });
    }
    const { data: allJobs } = await db.from("conversion_jobs").select("state");
    const counts = new Map<string, number>();
    for (const j of (allJobs ?? []) as Array<{ state: string }>) counts.set(j.state, (counts.get(j.state) ?? 0) + 1);
    states.push(...[...counts.entries()].map(([state, count]) => ({ state, count })));
  }

  return (
    <AdminShell>
      <div className="mx-auto max-w-6xl px-6 py-16">
        <h1 className="font-display text-4xl">Usage</h1>
        <p className="mt-2 text-neutral-400">Top users by conversions (last 5,000 jobs) and overall job state distribution.</p>
        <div className="mt-6 rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="text-neutral-400 border-b border-white/10">
              <tr><th className="px-4 py-3">User</th><th className="px-4 py-3">Jobs</th><th className="px-4 py-3">Failed</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-white/10 last:border-0">
                  <td className="px-4 py-3 font-medium">{r.email || r.id.slice(0, 8)}</td>
                  <td className="px-4 py-3 text-right">{r.jobs_total}</td>
                  <td className="px-4 py-3 text-right">{r.jobs_failed}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td className="px-4 py-6 text-neutral-500" colSpan={3}>{isDbConfigured() ? "No jobs yet" : "Database not connected."}</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="mt-6 space-y-2 rounded-xl border border-white/10 p-4">
          <h2 className="font-semibold">Job states</h2>
          {states.map((s) => (
            <div key={s.state}><span className="text-neutral-300">{s.state}:</span> {s.count}</div>
          ))}
        </div>
      </div>
    </AdminShell>
  );
}
