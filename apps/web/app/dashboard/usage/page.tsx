import { requireUser } from "@/lib/server-auth";
import { resolveQuotas } from "@/lib/quotas";

export const metadata = { title: "Usage" };

const PLAN_LABEL: Record<string, string> = {
  free: "Free",
  pro: "Pro",
  power: "Power",
  business: "Business",
};

export default async function UsagePage() {
  const { user } = await requireUser("/dashboard/usage");
  const quota = await resolveQuotas(user.id).catch(() => null);

  const planId = quota?.quotas.planId ?? "free";
  const rows = [
    {
      label: "Conversion pages",
      used: quota?.usedConversion ?? 0,
      limit: quota?.quotas.conversionPages ?? 0,
    },
    {
      label: "Verified pages",
      used: quota?.usedVerified ?? 0,
      limit: quota?.quotas.verifiedPages ?? 0,
    },
  ];

  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-display text-4xl">Usage</h1>
      <p className="mt-2 text-neutral-400">
        Plan {PLAN_LABEL[planId] ?? planId}. Usage counts conversions from the last 30 days.
      </p>

      <div className="mt-8 divide-y divide-white/10 rounded-2xl border border-white/10 bg-ink-soft">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-4 p-5">
            <span className="text-sm text-neutral-400">{row.label}</span>
            <span className="text-lg font-semibold">
              {row.used} / {row.limit}
            </span>
          </div>
        ))}
      </div>

      <p className="mt-6 text-xs text-neutral-500">
        Limits come from your plan and are enforced on the server.
      </p>
    </div>
  );
}
