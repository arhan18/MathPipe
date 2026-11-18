/**
 * @mathpipe/usage — quota checks and metering (§24–§25).
 *
 * Balances derive from the append-only usage_events trail — never from a
 * mutable counter. Quota decisions happen server-side before any expensive
 * work is enqueued.
 */

export type UsageKind =
  | "conversion_page_consumed"
  | "verification_page_consumed"
  | "extra_credit_consumed"
  | "credit_granted";

export interface PlanQuotas {
  planId: string;
  conversionPages: number;
  verifiedPages: number;
  maxFileMb: number;
  maxPagesPerJob: number;
  maxConcurrentJobs: number;
}

export interface UsageBalance {
  conversionUsed: number;
  conversionAllowed: number;
  verifiedUsed: number;
  verifiedAllowed: number;
  conversionRemaining: number;
  verifiedRemaining: number;
}

export function deriveBalance(
  quotas: PlanQuotas,
  events: Array<{ kind: UsageKind; quantity: number }>,
): UsageBalance {
  let conversionUsed = 0;
  let verifiedUsed = 0;
  for (const e of events) {
    if (e.kind === "conversion_page_consumed") conversionUsed += e.quantity;
    if (e.kind === "verification_page_consumed") verifiedUsed += e.quantity;
    if (e.kind === "extra_credit_consumed") conversionUsed += e.quantity;
    if (e.kind === "credit_granted") conversionUsed -= e.quantity;
  }
  conversionUsed = Math.max(0, conversionUsed);
  return {
    conversionUsed,
    conversionAllowed: quotas.conversionPages,
    verifiedUsed,
    verifiedAllowed: quotas.verifiedPages,
    conversionRemaining: Math.max(0, quotas.conversionPages - conversionUsed),
    verifiedRemaining: Math.max(0, quotas.verifiedPages - verifiedUsed),
  };
}

export type QuotaDecision =
  | { ok: true }
  | { ok: false; code: "QUOTA_EXCEEDED" | "PAGE_LIMIT_EXCEEDED"; message: string };

/** Authorize a conversion before any cost is incurred. No processing starts on failure. */
export function authorizeConversion(
  quotas: PlanQuotas,
  balance: UsageBalance,
  pages: number,
  mode: "standard" | "verified",
): QuotaDecision {
  if (pages < 1) {
    return { ok: false, code: "PAGE_LIMIT_EXCEEDED", message: "Document has no convertible pages." };
  }
  if (pages > quotas.maxPagesPerJob) {
    return {
      ok: false,
      code: "PAGE_LIMIT_EXCEEDED",
      message: `This document has ${pages} pages; your plan allows ${quotas.maxPagesPerJob} per job.`,
    };
  }
  if (balance.conversionRemaining < pages) {
    return {
      ok: false,
      code: "QUOTA_EXCEEDED",
      message: `You need ${pages - balance.conversionRemaining} more conversion pages for this document.`,
    };
  }
  if (mode === "verified" && balance.verifiedRemaining < pages) {
    return {
      ok: false,
      code: "QUOTA_EXCEEDED",
      message: "Not enough verification allowance — convert without verification or upgrade.",
    };
  }
  return { ok: true };
}

export function authorizeFileSize(quotas: PlanQuotas, sizeMb: number): QuotaDecision {
  if (sizeMb > quotas.maxFileMb) {
    return {
      ok: false,
      code: "PAGE_LIMIT_EXCEEDED",
      message: `This file is larger than your plan's ${quotas.maxFileMb} MB limit.`,
    };
  }
  return { ok: true };
}
