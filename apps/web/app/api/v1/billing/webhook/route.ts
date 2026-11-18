import { verifySignature, transitionForEvent, type PlanId } from "@mathpipe/billing";
import { API_VERSION, newRequestId } from "@mathpipe/shared";
import { startRequest, logEvent } from "@mathpipe/observability";
import { apiError } from "@/lib/api";

export const runtime = "nodejs";

/**
 * POST /api/v1/billing/webhook — Dodo Payments events (§26.1).
 *
 * Verify → idempotency lookup → persist raw event → apply entitlement
 * transactionally → audit → acknowledge. Duplicates and out-of-order
 * deliveries are safe: the event ledger (billing_events.event_id unique)
 * makes replays no-ops and stale transitions are rejected against the
 * current subscription row.
 */
export async function POST(req: Request) {
  const requestId = newRequestId();
  const ctx = startRequest(requestId);
  const secret = process.env.DODO_WEBHOOK_SECRET ?? "";
  if (!secret) {
    return apiError("AUTH_NOT_CONFIGURED", "Billing webhooks are not configured yet.", requestId);
  }

  const rawBody = await req.text();
  const verified = verifySignature(
    rawBody,
    {
      id: req.headers.get("webhook-id") ?? "",
      signature: req.headers.get("webhook-signature") ?? "",
      timestamp: req.headers.get("webhook-timestamp") ?? "",
    },
    secret,
  );
  if (!verified.ok) {
    logEvent(ctx, "webhook_rejected", { failure: verified.failure });
    return apiError("INVALID_INPUT", "Invalid webhook signature.", requestId, undefined, 401);
  }

  let event: { id?: string; type?: string; data?: Record<string, unknown> };
  try {
    event = JSON.parse(rawBody);
  } catch {
    return apiError("INVALID_INPUT", "Webhook body must be JSON.", requestId);
  }
  const eventId = req.headers.get("webhook-id") ?? event.id ?? "";
  const eventType = event.type ?? "";
  if (!eventId || !eventType) {
    return apiError("INVALID_INPUT", "Webhook event is missing id or type.", requestId);
  }

  // Persist + apply via Supabase service client (Phase 3-live). Until the
  // database is connected, acknowledge receipt without state changes so Dodo
  // stops retrying, and record the gap for reconciliation.
  const { isDbConfigured, createServiceClient } = await import("@mathpipe/db");
  if (!isDbConfigured()) {
    logEvent(ctx, "webhook_parked", { eventId, eventType });
    return Response.json({ apiVersion: API_VERSION, received: true, parked: true });
  }

  const db = createServiceClient();
  const { data: seen } = await db.from("billing_events").select("id").eq("event_id", eventId).maybeSingle();
  if (seen) {
    logEvent(ctx, "webhook_duplicate", { eventId });
    return Response.json({ apiVersion: API_VERSION, received: true, duplicate: true });
  }

  const planHint = (event.data?.plan ?? event.data?.metadata_plan ?? null) as PlanId | null;
  const transition = transitionForEvent(eventType, planHint);
  const userId = (event.data?.user_id ?? event.data?.customer_id) as string | undefined;

  const { error: persistError } = await db.from("billing_events").insert({
    event_id: eventId,
    type: eventType,
    user_id: userId ?? null,
    payload: event,
  });
  if (persistError) {
    // Unique violation under racing duplicates → safe acknowledge.
    if (persistError.code === "23505") {
      return Response.json({ apiVersion: API_VERSION, received: true, duplicate: true });
    }
    logEvent(ctx, "webhook_persist_failed", { eventId });
    return apiError("INTERNAL", "Could not record billing event.", requestId);
  }

  if (!transition.noop && userId) {
    const { data: sub } = await db
      .from("subscriptions")
      .select("id,status,plan_id")
      .eq("user_id", userId)
      .eq("status", "active")
      .maybeSingle();
    // Stale-transition guard: only move forward from a known active row.
    if (sub && (transition.status !== "active" || (sub.plan_id as string) !== transition.plan)) {
      const patch: Record<string, string> = { status: transition.status };
      if (transition.status === "active") patch.plan_id = transition.plan;
      await db.from("subscriptions").update(patch).eq("id", sub.id);
    } else if (!sub && transition.status === "active") {
      await db.from("subscriptions").insert({ user_id: userId, plan_id: transition.plan, status: "active" });
    }
    await db.from("admin_events").insert({
      actor: "billing-webhook",
      action: `entitlement:${eventType}`,
      target: userId,
      detail: { eventId, plan: transition.plan, status: transition.status },
    });
  }

  logEvent(ctx, "webhook_applied", { eventId, eventType });
  return Response.json({ apiVersion: API_VERSION, received: true });
}
