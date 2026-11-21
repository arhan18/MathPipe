import { isDbConfigured, createServiceClient } from "@mathpipe/db";
import { AdminShell } from "../gate";

export const metadata = { title: "Admin · Feedback" };
export const dynamic = "force-dynamic";

export default async function AdminFeedbackPage() {
  let rows = [] as Array<{ id: string; user: string; job: string | null; rating: string; category: string | null; comment: string | null; created: string }>;
  const dbReady = isDbConfigured();
  if (dbReady) {
    const db = createServiceClient();
    const { data } = await db.from("feedback").select("id,user_id,job_id,rating,category,comment,created_at").order("created_at", { ascending: false }).limit(100);
    const profiles = (await db.from("profiles").select("id,email").limit(500)).data ?? [];
    const emailByProfile = new Map((profiles as Array<{ id: string; email: string | null }>).filter((p) => p.email).map((p) => [p.id, p.email as string]));
    rows = (data ?? []).map((r: any) => ({
      id: r.id,
      user: emailByProfile.get(r.user_id) ?? r.user_id.slice(0, 8),
      job: r.job_id ? r.job_id.slice(0, 8) : null,
      rating: r.rating === true ? "up" : r.rating === false ? "down" : "none",
      category: r.category ?? null,
      comment: r.comment ?? null,
      created: r.created_at,
    }));
  }

  return (
    <AdminShell>
      <div className="mx-auto max-w-6xl px-6 py-16">
        <h1 className="font-display text-4xl">Feedback</h1>
        <p className="mt-2 text-neutral-400">User-reported conversion issues and ratings.</p>
        <div className="mt-6 space-y-3">
          {rows.map((r) => (
            <div key={r.id} className="rounded-xl border border-white/10 p-4">
              <div className="flex items-center justify-between">
                <p className="font-medium">{r.user}</p>
                <span className="text-xs text-neutral-500">{r.rating}</span>
              </div>
              {r.job && <p className="mt-1 text-sm text-neutral-500">Job: {r.job}</p>}
              {r.category && <p className="mt-1 text-sm text-neutral-400">{r.category}</p>}
              {r.comment && <p className="mt-2 text-sm">{r.comment}</p>}
              <p className="mt-1 text-xs text-neutral-500">{new Date(r.created).toLocaleString()}</p>
            </div>
          ))}
          {rows.length === 0 && <p className="text-neutral-500">{dbReady ? "No feedback yet." : "Database not connected."}</p>}
        </div>
      </div>
    </AdminShell>
  );
}
