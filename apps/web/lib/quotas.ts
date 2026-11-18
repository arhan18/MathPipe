import { createServiceClient } from "@mathpipe/db";
import { deriveBalance, authorizeConversion, authorizeFileSize, type PlanQuotas } from "@mathpipe/usage";

/**
 * Server-side quota resolution: active subscription → plan quotas → live
 * balance from the usage ledger. No plan row means Free.
 */
export async function resolveQuotas(userId: string): Promise<{ quotas: PlanQuotas; usedConversion: number; usedVerified: number }> {
  const fallback: PlanQuotas = {
    planId: "free", conversionPages: 10, verifiedPages: 0,
    maxFileMb: 25, maxPagesPerJob: 25, maxConcurrentJobs: 1,
  };
  if (process.env.NEXT_PUBLIC_SUPABASE_URL === undefined && process.env.SUPABASE_URL === undefined) {
    return { quotas: fallback, usedConversion: 0, usedVerified: 0 };
  }
  try {
    const db = createServiceClient();
    const { data: sub } = await db
      .from("subscriptions").select("plan_id").eq("user_id", userId).eq("status", "active")
      .maybeSingle();
    const planId = (sub?.plan_id as string) ?? "free";
    const { data: plan } = await db.from("plans").select("*").eq("id", planId).maybeSingle();
    const quotas: PlanQuotas = plan
      ? {
          planId, conversionPages: plan.conversion_pages, verifiedPages: plan.verified_pages,
          maxFileMb: plan.max_file_mb, maxPagesPerJob: plan.max_pages_per_job,
          maxConcurrentJobs: plan.max_concurrent_jobs,
        }
      : fallback;
    const since = new Date(Date.now() - 30 * 24 * 3600 * 1000).toISOString();
    const { data: events } = await db
      .from("usage_events").select("kind,quantity").eq("user_id", userId).gte("created_at", since);
    const balance = deriveBalance(quotas, (events ?? []) as Array<{ kind: never; quantity: number }>);
    return { quotas, usedConversion: balance.conversionUsed, usedVerified: balance.verifiedUsed };
  } catch {
    return { quotas: fallback, usedConversion: 0, usedVerified: 0 };
  }
}

export { authorizeConversion, authorizeFileSize, deriveBalance };
