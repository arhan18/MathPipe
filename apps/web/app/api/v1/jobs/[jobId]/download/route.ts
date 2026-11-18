import { newRequestId } from "@mathpipe/shared";
import { getJobStore, requireUser, checkLimit, apiError } from "@/lib/api";
import { getObjectStorage } from "@/lib/storage";
import { API_VERSION } from "@mathpipe/shared";
import { createServiceClient, isDbConfigured } from "@mathpipe/db";

export const runtime = "nodejs";

/** GET /api/v1/jobs/[jobId]/download — ownership-checked signed URL. */
export async function GET(req: Request, { params }: { params: Promise<{ jobId: string }> }) {
  const requestId = newRequestId();
  const { jobId } = await params;
  const limited = checkLimit(req, "download");
  if (!limited.ok) return limited.response;

  const auth = await requireUser();
  if ("response" in auth) return auth.response;

  const job = await getJobStore().get(jobId);
  if (!job || job.userId !== auth.user.id) {
    return apiError("NOT_FOUND", "No such job.", requestId);
  }
  if (job.state !== "completed" && job.state !== "completed_with_warnings") {
    return apiError("INVALID_INPUT", `Document is not ready (state: ${job.state}).`, requestId);
  }

  // Newest output artifact wins.
  let key: string | null = null;
  if (isDbConfigured()) {
    const db = createServiceClient();
    const { data } = await db
      .from("conversion_artifacts")
      .select("storage_key")
      .eq("job_id", jobId)
      .eq("kind", "output")
      .is("deleted_at", null)
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    key = (data?.storage_key as string) ?? null;
  }
  if (!key) {
    return apiError("NOT_FOUND", "No finished document for this job yet.", requestId);
  }
  const url = await getObjectStorage().presignedDownloadUrl(key, 3600);
  return Response.json({ apiVersion: API_VERSION, url, expiresIn: 3600 });
}
