import { newRequestId } from "@mathpipe/shared";
import { requireUser, checkLimit, apiError } from "@/lib/api";

export const runtime = "nodejs";

/**
 * POST /api/v1/billing/checkout — start a Dodo checkout session.
 *
 * Scaffold: answers 503 until DODO_API_KEY exists (Phase 9-live wires the
 * Dodo checkout API with plan → product mapping). Never grants entitlements —
 * those come only from verified webhooks.
 */
export async function POST(req: Request) {
  const requestId = newRequestId();
  const limited = checkLimit(req, "jobs");
  if (!limited.ok) return limited.response;

  const auth = await requireUser();
  if ("response" in auth) return auth.response;

  if (!process.env.DODO_API_KEY) {
    return apiError("AUTH_NOT_CONFIGURED", "Checkout is not configured yet.", requestId);
  }
  return apiError("INTERNAL", "Checkout product mapping is not configured yet.", requestId);
}
