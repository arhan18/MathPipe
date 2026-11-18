import { randomUUID } from "node:crypto";
import { validateCreateInput, toSnapshot } from "@mathpipe/jobs";
import { API_VERSION, newRequestId } from "@mathpipe/shared";
import { startRequest, logEvent } from "@mathpipe/observability";
import { getJobStore, requireUser, checkLimit, apiError } from "@/lib/api";

export const runtime = "nodejs";

/** POST /api/v1/jobs — create a conversion job (idempotent). */
export async function POST(req: Request) {
  const requestId = newRequestId();
  const limited = checkLimit(req, "jobs");
  if (!limited.ok) return limited.response;

  const auth = await requireUser();
  if ("response" in auth) return auth.response;

  let body: unknown = null;
  try {
    body = await req.json();
  } catch {
    return apiError("INVALID_INPUT", "Request body must be JSON.", requestId);
  }
  const b = body as Record<string, unknown>;
  const validated = validateCreateInput({
    id: randomUUID(),
    userId: auth.user.id,
    sourceFileId: typeof b.sourceFileId === "string" ? b.sourceFileId : "",
    mode: b.mode as "standard" | "verified",
    pageRange: typeof b.pageRange === "string" ? b.pageRange : null,
    idempotencyKey: req.headers.get("Idempotency-Key") ?? "",
  });
  if (!validated.ok) return apiError(validated.code, validated.message, requestId);

  const ctx = startRequest(requestId, { userId: auth.user.id });
  const { job, replayed } = await getJobStore().create(validated.value);
  logEvent(ctx, replayed ? "job_replayed" : "job_created", { jobId: job.id, mode: job.mode });
  return Response.json({ apiVersion: API_VERSION, job: toSnapshot(job) }, { status: replayed ? 200 : 201 });
}
