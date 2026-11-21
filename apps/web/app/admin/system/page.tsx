import { isDbConfigured, createServiceClient } from "@mathpipe/db";
import { AdminShell } from "../gate";

export const metadata = { title: "Admin · System" };
export const dynamic = "force-dynamic";

interface Stat { label: string; value: string; }

export default async function AdminSystemPage() {
  const stats: Stat[] = [];
  const concerns: Array<{ job: string; state: string; updated: string; age: string }> = [];
  if (isDbConfigured()) {
    const db = createServiceClient();
    const [jobs, stalled, errs] = await Promise.all([
      db.from("conversion_jobs").select("id,state,updated_at").order("updated_at", { ascending: false }).limit(50),
      db.from("conversion_jobs").select("id,state,updated_at,error_code").in("state", ["analyzing", "processing", "reconstructing", "finalizing"]).limit(20),
      db.from("conversion_jobs").select("error_code,count").gte("updated_at", new Date(Date.now() - 86_400_000).toISOString()).order("count", { ascending: false }).limit(10),
    ]);
    stats.push({ label: "Queue depth", value: String((jobs.data ?? []).length) });
    stats.push({ label: "Last job updated", value: (jobs.data?.[0]?.updated_at as string)?.slice(0, 16) ?? "—" });
    for (const j of (stalled.data ?? []) as Array<{ id: string; state: string; updated_at: string; error_code: string | null }>) {
      const ageMin = Math.max(0, Math.round((Date.now() - Date.parse(j.updated_at)) / 60_000));
      concerns.push({ job: j.id.slice(0, 8), state: j.state, updated: j.updated_at, age: `~${ageMin}m` });
    }
    const errData = (errs.data ?? []) as Array<{ error_code: string | null; count: number }>;
    stats.push({ label: "Errors (24h)", value: errData.map((r) => `${r.error_code ?? "n/a"}:${r.count}`).join(", ") || "none" });
  }

  return (
    <AdminShell>
      <div className="mx-auto max-w-6xl px-6 py-16">
        <h1 className="font-display text-4xl">System</h1>
        <p className="mt-2 text-neutral-400">Queue health and errors. Jobs stuck in a working state above ~30 min get requeued by the poller.</p>
        <div className="mt-6 rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="text-neutral-400 border-b border-white/10">
              <tr><th className="px-4 py-3">Metric</th><th className="px-4 py-3">Value</th></tr>
            </thead>
            <tbody>
              {stats.map((s) => (
                <tr key={s.label} className="border-b border-white/10 last:border-0">
                  <td className="px-4 py-3 text-neutral-400">{s.label}</td>
                  <td className="px-4 py-3 font-semibold">{s.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h2 className="mt-8 font-semibold">Working-state concerns (idle 30+ min)</h2>
        {concerns.length ? (
          <div className="mt-3 space-y-2">
            {concerns.map((c) => (
              <div key={c.job} className="rounded-lg border border-white/10 p-3 text-sm">
                <span className="font-mono text-neutral-300">{c.job}</span> {c.state} — idle since {c.updated.slice(0, 16)} ({c.age})
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-neutral-500">Nothing stalled.</p>
        )}
      </div>
    </AdminShell>
  );
}
