/**
 * @mathpipe/billing — Dodo Payments integration (§26).
 *
 * Webhooks follow the Standard Webhooks spec: webhook-id / webhook-signature
 * (space-separated v1,<base64> entries) / webhook-timestamp headers over the
 * EXACT raw body bytes. Entitlements change only from verified webhooks —
 * never from client-side success screens.
 */

import { createHmac, timingSafeEqual } from "node:crypto";

export interface WebhookHeaders {
  id: string;
  signature: string;
  timestamp: string;
}

export type VerifyFailure =
  | "missing_headers"
  | "bad_signature"
  | "stale_timestamp"
  | "bad_payload";

/** Seconds of clock skew tolerated (replay protection). */
export const TIMESTAMP_TOLERANCE_S = 300;

/** Strip the `whsec_` prefix Dodo dashboard secrets carry, if present. */
export function normalizeSecret(secret: string): string {
  return secret.startsWith("whsec_") ? secret.slice("whsec_".length) : secret;
}

export function signPayload(secret: string, id: string, timestamp: string, rawBody: string): string {
  const content = `${id}.${timestamp}.${rawBody}`;
  return createHmac("sha256", normalizeSecret(secret)).update(content, "utf8").digest("base64");
}

export function verifySignature(
  rawBody: string,
  headers: WebhookHeaders,
  secret: string,
  nowS: number = Math.floor(Date.now() / 1000),
): { ok: true } | { ok: false; failure: VerifyFailure } {
  if (!headers.id || !headers.signature || !headers.timestamp) {
    return { ok: false, failure: "missing_headers" };
  }
  const ts = Number(headers.timestamp);
  if (!Number.isFinite(ts) || Math.abs(nowS - ts) > TIMESTAMP_TOLERANCE_S) {
    return { ok: false, failure: "stale_timestamp" };
  }
  const expected = signPayload(secret, headers.id, headers.timestamp, rawBody);
  const candidates = headers.signature.split(" ").filter(Boolean);
  for (const candidate of candidates) {
    const [version, sig] = candidate.split(",", 2);
    if (version !== "v1" || !sig) continue;
    const a = Buffer.from(sig, "base64");
    const b = Buffer.from(expected, "base64");
    if (a.length === b.length && timingSafeEqual(a, b)) return { ok: true };
  }
  return { ok: false, failure: "bad_signature" };
}

// Entitlements --------------------------------------------------------------

export type PlanId = "free" | "pro" | "power" | "business";
export type SubscriptionStatus = "active" | "cancelled" | "past_due" | "trialing";

/** Dodo event types we act on. Unknown types acknowledge without state change. */
export type HandledEvent =
  | "subscription.active"
  | "subscription.renewed"
  | "subscription.cancelled"
  | "subscription.expired"
  | "payment.succeeded"
  | "payment.failed"
  | "payment.refunded";

export interface EntitlementTransition {
  plan: PlanId;
  status: SubscriptionStatus;
  /** True when the event carries no state change (informational/unknown). */
  noop: boolean;
}

/**
 * Map a verified Dodo event to an entitlement transition.
 * planHint comes from checkout metadata (metadata.plan); unknown mappings
 * never upgrade — they noop for manual review.
 */
export function transitionForEvent(
  eventType: string,
  planHint: PlanId | null,
): EntitlementTransition {
  switch (eventType) {
    case "subscription.active":
    case "subscription.renewed":
      if (planHint && planHint !== "free") {
        return { plan: planHint, status: "active", noop: false };
      }
      return { plan: "free", status: "active", noop: true };
    case "payment.failed":
      return { plan: "free", status: "past_due", noop: false };
    case "subscription.cancelled":
    case "subscription.expired":
      return { plan: "free", status: "cancelled", noop: false };
    case "payment.succeeded":
    case "payment.refunded":
    default:
      return { plan: "free", status: "active", noop: true };
  }
}
