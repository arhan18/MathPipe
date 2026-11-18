import Link from "next/link";
import { AdminShell } from "./gate";

export const metadata = { title: "Admin" };

const LINKS = [
  { href: "/admin/jobs", title: "Jobs", body: "Conversion states, timings, failures, retries." },
  { href: "/admin/usage", title: "Usage", body: "Plan consumption and quota pressure." },
  { href: "/admin/billing", title: "Billing", body: "Subscription states and webhook ledger." },
  { href: "/admin/feedback", title: "Feedback", body: "User-reported conversion issues." },
  { href: "/admin/system", title: "System", body: "Queue depth, provider health, spend guards." },
];

export default async function AdminPage() {
  return (
    <AdminShell>
      <div className="mx-auto max-w-6xl px-6 py-16">
        <h1 className="font-display text-4xl">Operations</h1>
        <p className="mt-2 text-neutral-400">Metadata only. File contents are never shown here.</p>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="rounded-2xl border border-white/10 bg-ink-soft p-6 transition-colors hover:border-white/25">
              <p className="font-semibold">{l.title}</p>
              <p className="mt-1 text-sm text-neutral-400">{l.body}</p>
            </Link>
          ))}
        </div>
      </div>
    </AdminShell>
  );
}
