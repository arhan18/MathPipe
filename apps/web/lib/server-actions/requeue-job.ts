"use server";

import { createServiceClient, isDbConfigured } from "@mathpipe/db";
import { requireAdmin } from "@/app/admin/gate";

export type RequeueResult = { ok: boolean; error: string | null };

export async function requeueJob(formData: FormData): Promise<RequeueResult> {
  const jobId = String(formData.get("jobId") ?? "");
  if (!jobId) return { ok: false, error: "Missing jobId." };
  const admin = await requireAdmin();
  if ("denied" in admin) return { ok: false, error: admin.denied };
  if (!isDbConfigured()) return { ok: false, error: "Database not connected." };
  const db = createServiceClient();
  const { data } = await db.from("conversion_jobs").select("id,state").eq("id", jobId).maybeSingle();
  if (!data) return { ok: false, error: "Job not found." };
  const stuck = ["analyzing", "processing", "reconstructing", "finalizing", "queued", "uploaded", "validating"];
  if (!stuck.includes(data.state)) return { ok: false, error: `Job is not requeueable while "${data.state}".` };
  await db.from("conversion_jobs").update({ state: "queued", error_code: null, retryable: true }).eq("id", jobId).eq("state", data.state);
  return { ok: true, error: null };
}
