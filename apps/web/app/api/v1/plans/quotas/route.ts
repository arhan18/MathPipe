import { newRequestId } from "@mathpipe/shared";
import { requireUser } from "@/lib/api";
import { resolveQuotas } from "@/lib/quotas";

export const runtime = "nodejs";

/**
 * GET /api/v1/plans/quotas — plan + quotas for the signed-in user.
 * Client helper for batch-upload gating (Business has batch enabled).
 */
export async function GET() {
  const requestId = newRequestId();
  const auth = await requireUser();
  if ("response" in auth) return auth.response;
  const quota = await resolveQuotas(auth.user.id);
  return Response.json({
    apiVersion: "1",
    quotas: quota.quotas,
    usedConversion: quota.usedConversion,
    usedVerified: quota.usedVerified,
    requestId,
  });
}
