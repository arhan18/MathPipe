import { requireUser } from "@/lib/server-auth";
import { resolveQuotas } from "@/lib/quotas";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { SignOutButton } from "@/components/sign-out-button";

export const metadata = { title: "Dashboard" };

const PLAN_LABEL: Record<string, string> = {
  free: "Free",
  pro: "Pro",
  power: "Power",
  business: "Business",
};

const STATE_LABEL: Record<string, string> = {
  uploaded: "Uploaded",
  validating: "Validating",
  queued: "Queued",
  analyzing: "Analyzing",
  processing: "Processing",
  reconstructing: "Reconstructing",
  verifying: "Verifying",
  repairing: "Repairing",
  finalizing: "Finalizing",
  completed: "Ready",
  completed_with_warnings: "Ready with warnings",
  failed: "Failed",
  cancelled: "Cancelled",
  expired: "Expired",
};

interface JobRow {
  id: string;
  state: string;
  created_at: string;
}

export default async function DashboardPage() {
  const { supabase, user } = await requireUser("/dashboard");

  const [quota, jobsResult] = await Promise.all([
    resolveQuotas(user.id).catch(() => null),
    supabase
      .from("conversion_jobs")
      .select("id,state,created_at")
      .order("created_at", { ascending: false })
      .limit(3),
  ]);

  const jobs = (jobsResult.data ?? []) as JobRow[];
  const planId = quota?.quotas.planId ?? "free";
  const conversionLimit = quota?.quotas.conversionPages ?? 0;
  const verifiedLimit = quota?.quotas.verifiedPages ?? 0;
  const conversionUsed = quota?.usedConversion ?? 0;
  const verifiedUsed = quota?.usedVerified ?? 0;

  return (
    <div className="mx-auto max-w-6xl px-6 py-16">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl">Welcome back.</h1>
          {user.email ? (
            <p className="mt-1 text-sm text-neutral-400">{user.email}</p>
          ) : null}
        </div>
        <SignOutButton />
      </div>
      <div className="mt-4 flex flex-wrap gap-3">
        <Button asChild><Link href="/convert">Convert a PDF</Link></Button>
        <Button variant="outline" asChild><Link href="/dashboard/billing">Manage plan</Link></Button>
      </div>

      <div className="mt-8 grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-white/10 bg-ink-soft p-6">
          <p className="text-sm text-neutral-400">Current plan</p>
          <p className="mt-1 text-2xl font-semibold">{PLAN_LABEL[planId] ?? planId}</p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-ink-soft p-6">
          <p className="text-sm text-neutral-400">Conversion pages used</p>
          <p className="mt-1 text-2xl font-semibold">
            {conversionUsed} / {conversionLimit}
          </p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-ink-soft p-6">
          <p className="text-sm text-neutral-400">Verified pages used</p>
          <p className="mt-1 text-2xl font-semibold">
            {verifiedUsed} / {verifiedLimit}
          </p>
        </div>
      </div>

      <h2 className="mt-10 text-xl font-semibold">Recent conversions</h2>
      {jobs.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-white/10 bg-ink-soft p-8 text-center text-neutral-400">
          <p>No conversions yet.</p>
          <Button variant="outline" className="mt-4" asChild>
            <Link href="/convert">Convert your first PDF</Link>
          </Button>
        </div>
      ) : (
        <ul className="mt-4 divide-y divide-white/10 rounded-2xl border border-white/10 bg-ink-soft">
          {jobs.map((job) => (
            <li key={job.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
              <span className="font-mono text-sm text-neutral-300">{job.id.slice(0, 8)}</span>
              <span className="text-sm text-neutral-400">{STATE_LABEL[job.state] ?? job.state}</span>
              <span className="text-xs text-neutral-500">
                {new Date(job.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      )}
      {jobs.length > 0 ? (
        <div className="mt-4">
          <Button variant="outline" asChild>
            <Link href="/dashboard/history">View all conversions</Link>
          </Button>
        </div>
      ) : null}
    </div>
  );
}
