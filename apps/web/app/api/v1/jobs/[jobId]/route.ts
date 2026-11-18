import { toSnapshot } from "@mathpipe/jobs";
import { API_VERSION, newRequestId } from "@mathpipe/shared";
import { getJobStore, requireUser, checkLimit, apiError } from "@/lib/api";

export const runtime = "nodejs";

/** GET /api/v1/jobs/[jobId] — authoritative snapshot (polling fallback, §21.1). */
export async function GET(req: Request, { params }: { params: Promise<{ jobId: string }> }) {
  const requestId = newRequestId();
  const { jobId } = await params;
  const limited = checkLimit(req, "poll");
  if (!limited.ok) return limited.response;

  const auth = await requireUser();
  if ("response" in auth) return auth.response;

  const job = await getJobStore().get(jobId);
  if (!job || job.userId !== auth.user.id) {
    return apiError("NOT_FOUND", "No such job.", requestId);
  }
  return Response.json({ apiVersion: API_VERSION, job: toSnapshot(job) });
}
