import { API_VERSION, newRequestId } from "@mathpipe/shared";
import { getJobStore, requireUser, checkLimit, apiError } from "@/lib/api";
import { createServiceClient, ensureProfile } from "@mathpipe/db";

export const runtime = "nodejs";

/** POST /api/v1/feedback — { jobId, rating: boolean, comment? }. */
export async function POST(req: Request) {
  const requestId = newRequestId();
  const limited = checkLimit(req, "feedback");
  if (!limited.ok) return limited.response;

  const auth = await requireUser();
  if ("response" in auth) return auth.response;

  let body: { jobId?: unknown; rating?: unknown; comment?: unknown };
  try {
    body = await req.json();
  } catch {
    return apiError("INVALID_INPUT", "Request must be JSON.", requestId);
  }
  if (typeof body.jobId !== "string" || typeof body.rating !== "boolean") {
    return apiError("INVALID_INPUT", "Fields required: jobId (string), rating (boolean).", requestId);
  }
  const comment = typeof body.comment === "string" ? body.comment.slice(0, 2000) : null;

  const job = await getJobStore().get(body.jobId);
  if (!job || job.userId !== auth.user.id) {
    return apiError("NOT_FOUND", "Job not found.", requestId, undefined, 404);
  }

  const db = createServiceClient();
  await ensureProfile(db, auth.user.id);
  const { error } = await db.from("feedback").insert({
    user_id: auth.user.id, job_id: job.id, rating: body.rating, comment,
  });
  if (error) return apiError("INTERNAL", "Could not save feedback. Please retry.", requestId);
  return Response.json({ apiVersion: API_VERSION, ok: true }, { status: 201 });
}
