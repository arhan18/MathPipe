import { requireUser } from "@/lib/server-auth";
import { resolveQuotas } from "@/lib/quotas";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export const metadata = { title: "Billing" };

const PLAN_LABEL: Record<string, string> = {
  free: "Free",
  pro: "Pro",
  power: "Power",
  business: "Business",
};

export default async function BillingPage() {
  const { user } = await requireUser("/dashboard/billing");
  const quota = await resolveQuotas(user.id).catch(() => null);

  const planId = quota?.quotas.planId ?? "free";
  const conversionLimit = quota?.quotas.conversionPages ?? 0;

  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-display text-4xl">Billing</h1>

      <div className="mt-8 rounded-2xl border border-white/10 bg-ink-soft p-6">
        <p className="text-sm text-neutral-400">Current plan</p>
        <p className="mt-1 text-2xl font-semibold">{PLAN_LABEL[planId] ?? planId}</p>
        <p className="mt-1 text-sm text-neutral-400">
          {conversionLimit} conversion pages per 30 days
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Button asChild><Link href="/pricing">Compare plans</Link></Button>
          <Button variant="outline" asChild><Link href="/dashboard/usage">View usage</Link></Button>
        </div>
      </div>

      <div className="mt-6 rounded-2xl border border-white/10 bg-ink-soft p-6">
        <h2 className="font-semibold">Invoices</h2>
        <p className="mt-1 text-sm text-neutral-400">
          No invoices yet. They appear here after your first payment.
        </p>
      </div>

      <p className="mt-6 text-xs text-neutral-500">
        Payments are processed by Dodo Payments. Entitlements update only from verified
        payment webhooks — never from anything shown in your browser.
      </p>
    </div>
  );
}
