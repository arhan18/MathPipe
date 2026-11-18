import { randomUUID } from "node:crypto";
import { API_VERSION, newRequestId } from "@mathpipe/shared";
import { toSnapshot } from "@mathpipe/jobs";
import { startRequest, logEvent } from "@mathpipe/observability";
import { getJobStore, requireUser, checkLimit, apiError } from "@/lib/api";
import { getObjectStorage } from "@/lib/storage";
import { storageKey } from "@mathpipe/storage";
import { resolveQuotas, authorizeConversion, authorizeFileSize } from "@/lib/quotas";
import { countPdfPages, looksLikePdf } from "@/lib/pdf";
import { createServiceClient, ensureProfile } from "@mathpipe/db";

export const runtime = "nodejs";

/**
 * POST /api/v1/uploads — multipart { file, mode, pageRange?, idempotencyKey }.
 * Validates → stores source → creates the job → returns it. The processor
 * picks the job up from the jobs table (Modal webhook, Phase 9-ops).
 */
export async function POST(req: Request) {
  const requestId = newRequestId();
  const limited = checkLimit(req, "upload");
  if (!limited.ok) return limited.response;

  const auth = await requireUser();
  if ("response" in auth) return auth.response;
  const ctx = startRequest(requestId, { userId: auth.user.id });

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return apiError("INVALID_INPUT", "Request must be multipart form data.", requestId);
  }
  const file = form.get("file");
  const mode = form.get("mode");
  const pageRange = form.get("pageRange");
  const idempotencyKey = form.get("idempotencyKey");
  if (!(file instanceof Blob) || (mode !== "standard" && mode !== "verified")) {
    return apiError("INVALID_INPUT", "Fields required: file (PDF), mode (standard|verified).", requestId);
  }

  const bytes = new Uint8Array(await file.arrayBuffer());
  if (!looksLikePdf(bytes)) {
    return apiError("FILE_INVALID", "That file is not a PDF.", requestId);
  }

  const { quotas, usedConversion, usedVerified } = await resolveQuotas(auth.user.id);
  const sizeMb = bytes.length / 1024 / 1024;
  const sizeCheck = authorizeFileSize(quotas, sizeMb);
  if (!sizeCheck.ok) return apiError(sizeCheck.code, sizeCheck.message, requestId);

  const pages = await countPdfPages(bytes);
  if (pages !== null) {
    const quota = authorizeConversion(
      quotas,
      {
        conversionUsed: usedConversion, conversionAllowed: quotas.conversionPages,
        verifiedUsed: usedVerified, verifiedAllowed: quotas.verifiedPages,
        conversionRemaining: Math.max(0, quotas.conversionPages - usedConversion),
        verifiedRemaining: Math.max(0, quotas.verifiedPages - usedVerified),
      },
      pages,
      mode,
    );
    if (!quota.ok) return apiError(quota.code, quota.message, requestId);
  }

  const jobId = randomUUID();
  const key = storageKey(auth.user.id, jobId, "source.pdf");
  try {
    await getObjectStorage().put(key, bytes, { contentType: "application/pdf" });
  } catch (e) {
    logEvent(ctx, "upload_store_failed", {});
    return apiError("INTERNAL", "Could not store the upload. Please retry.", requestId);
  }

  const store = getJobStore();
  // Profile bootstrap: signups create auth.users rows but no profiles row
  // (trigger migration 2026100605 covers future envs); without this the
  // conversion_jobs FK rejects the insert for every first-time user.
  await ensureProfile(createServiceClient(), auth.user.id);
  const { job } = await store.create({
    id: jobId,
    userId: auth.user.id,
    sourceFileId: key,
    mode,
    pageRange: typeof pageRange === "string" && pageRange ? pageRange : null,
    idempotencyKey: typeof idempotencyKey === "string" && idempotencyKey ? idempotencyKey : randomUUID(),
  });
  // Record the artifact + walk the legal entry chain (uploaded → validating
  // → queued). The processor takes the job up from queued (→ analyzing).
  const v = await store.transition(job.id, "validating");
  if (!v) return apiError("INTERNAL", "Could not start the job. Please retry.", requestId);
  const q = await store.transition(job.id, "queued");
  const current = q ?? (await store.get(job.id));
  logEvent(ctx, "job_created", { jobId: job.id, mode, pages: pages ?? -1 });

  // Dispatch to the processor when deployed; otherwise the job waits in
  // validating and the UI shows its resting stage honestly.
  const webhook = process.env.MODAL_WEBHOOK_URL ?? "";
  if (webhook) {
    try {
      await fetch(webhook, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(process.env.MATHPIPE_WORKER_SECRET
            ? { "x-worker-secret": process.env.MATHPIPE_WORKER_SECRET }
            : {}),
        },
        body: JSON.stringify({
          job_id: job.id,
          source_bucket: "mathpipe-files",
          source_key: key,
          mode,
          page_range: typeof pageRange === "string" && pageRange ? pageRange : null,
        }),
        signal: AbortSignal.timeout(10000),
      });
    } catch (e) {
      logEvent(ctx, "processor_dispatch_failed", { jobId: job.id });
    }
  }
  return Response.json(
    { apiVersion: API_VERSION, job: toSnapshot(current ?? job), pages },
    { status: 201 },
  );
}
