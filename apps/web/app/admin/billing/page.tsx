import { isDbConfigured, createServiceClient } from "@mathpipe/db";
import { AdminShell } from "../gate";

export const metadata = { title: "Admin · Billing" };
export const dynamic = "force-dynamic";

interface BillingRow { id: string; plan_id: string; status: string; period_end: string | null; emails: string[]; }

export default async function AdminBillingPage() {
  const rows: BillingRow[] = [];
  if (isDbConfigured()) {
    const db = createServiceClient();
    const { data } = await db.from("subscriptions").select("id,plan_id,status,current_period_end,user_id").order("created_at", { ascending: false }).limit(50);
    const profiles = (await db.from("profiles").select("id,email").limit(500)).data ?? [];
    const emailByProfile = new Map((profiles as Array<{ id: string; email: string | null }>).filter((p) => p.email).map((p) => [p.id, p.email as string]));
    for (const s of (data ?? []) as Array<{ id: string; plan_id: string; status: string; current_period_end: string | null; user_id: string }>) {
      rows.push({ id: s.id, plan_id: s.plan_id, status: s.status, period_end: s.current_period_end, emails: [emailByProfile.get(s.user_id) ?? s.user_id.slice(0, 8)] });
    }
  }

  return (
    <AdminShell>
      <div className="mx-auto max-w-6xl px-6 py-16">
        <h1 className="font-display text-4xl">Billing</h1>
        <p className="mt-2 text-neutral-400">Active subscriptions: plan, status and expiry period.</p>
        <div className="mt-6 overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="text-neutral-400 border-b border-white/10">
              <tr><th className="px-4 py-3">User</th><th className="px-4 py-3">Plan</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Expires</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-white/10 last:border-0">
                  <td className="px-4 py-3 font-medium">{r.emails[0]}</td>
                  <td className="px-4 py-3">{r.plan_id}</td>
                  <td className="px-4 py-3">{r.status}</td>
                  <td className="px-4 py-3">{r.period_end ? new Date(r.period_end).toLocaleDateString() : "—"}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td className="px-4 py-6 text-neutral-500" colSpan={4}>{isDbConfigured() ? "No subscriptions yet" : "Database not connected."}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </AdminShell>
  );
}
