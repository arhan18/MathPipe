/**
 * @mathpipe/db — Supabase clients, Supabase-backed JobStore, usage ledger.
 *
 * Server-only. Never import the service-role client from browser code.
 * All writes go through RLS-aware user clients or the explicitly-elevated
 * service client inside trusted server paths.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import {
  canTransition,
  toSnapshot,
  type ConversionJob,
  type ConversionMode,
  type CreateJobInput,
  type ErrorCode,
  type JobEvent,
  type JobSnapshot,
  type JobState,
  type JobStore,
} from "@mathpipe/jobs";

export function supabaseUrl(): string | undefined {
  return process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
}

export function isDbConfigured(): boolean {
  return Boolean(supabaseUrl() && (process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY));
}

/** Service-role client for trusted server paths (bypasses RLS — use with care). */
export function createServiceClient(): SupabaseClient {
  const url = supabaseUrl();
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error("Supabase service credentials are not configured.");
  return createClient(url, key, { auth: { persistSession: false } });
}

/**
 * Idempotent profile bootstrap. Auth signups do not create `profiles` rows by
 * themselves (see migration `2026100605_profile_trigger.sql` for the
 * trigger-based path); every server path that writes user-scoped rows must
 * call this first or the FK on `conversion_jobs.user_id` rejects the write.
 */
export async function ensureProfile(
  db: SupabaseClient,
  userId: string,
  displayName?: string | null,
): Promise<void> {
  const { error } = await db
    .from("profiles")
    .upsert({ id: userId, display_name: displayName ?? null }, { onConflict: "id", ignoreDuplicates: true });
  if (error) throw new Error(`profile bootstrap failed: ${error.message}`);
}

interface JobRow {
  id: string;
  user_id: string;
  source_file_id: string;
  source_artifact_key: string | null;
  mode: ConversionMode;
  page_range: string | null;
  state: JobState;
  error_code: ErrorCode | null;
  retryable: boolean;
  warning_count: number;
  artifact_id: string | null;
  sequence: number;
  idempotency_key: string | null;
  created_at: string;
  updated_at: string;
}

function toJob(row: JobRow): ConversionJob {
  return {
    id: row.id,
    userId: row.user_id,
    sourceFileId: row.source_file_id,
    mode: row.mode,
    pageRange: row.page_range,
    state: row.state,
    errorCode: row.error_code,
    retryable: row.retryable,
    warningCount: row.warning_count,
    artifactId: row.artifact_id,
    sequence: row.sequence,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export class SupabaseJobStore implements JobStore {
  constructor(private db: SupabaseClient = createServiceClient()) {}

  async create(input: CreateJobInput): Promise<{ job: ConversionJob; replayed: boolean }> {
    const { data: existing } = await this.db
      .from("conversion_jobs")
      .select("*")
      .eq("idempotency_key", input.idempotencyKey)
      .maybeSingle();
    if (existing) return { job: toJob(existing as JobRow), replayed: true };
    const { data, error } = await this.db
      .from("conversion_jobs")
      .insert({
        id: input.id,
        user_id: input.userId,
        source_file_id: input.sourceFileId,
        source_artifact_key: input.sourceFileId,
        mode: input.mode,
        page_range: input.pageRange,
        state: "uploaded",
        idempotency_key: input.idempotencyKey,
      })
      .select("*")
      .single();
    if (error || !data) throw new Error(`job create failed: ${error?.message ?? "unknown"}`);
    return { job: toJob(data as JobRow), replayed: false };
  }

  async get(jobId: string): Promise<ConversionJob | null> {
    const { data } = await this.db.from("conversion_jobs").select("*").eq("id", jobId).maybeSingle();
    return data ? toJob(data as JobRow) : null;
  }

  async transition(
    jobId: string,
    to: JobState,
    patch?: Partial<Pick<ConversionJob, "errorCode" | "retryable" | "warningCount" | "artifactId">>,
  ): Promise<ConversionJob | null> {
    const current = await this.get(jobId);
    if (!current) return null;
    if (!canTransition(current.state, to)) return null;
    const { data, error } = await this.db
      .from("conversion_jobs")
      .update({
        state: to,
        error_code: patch?.errorCode ?? current.errorCode,
        retryable: patch?.retryable ?? current.retryable,
        warning_count: patch?.warningCount ?? current.warningCount,
        artifact_id: patch?.artifactId ?? current.artifactId,
        sequence: current.sequence + 1,
        updated_at: new Date().toISOString(),
      })
      .eq("id", jobId)
      .eq("sequence", current.sequence)
      .select("*")
      .maybeSingle();
    if (error || !data) return null;
    return toJob(data as JobRow);
  }

  async appendEvent(jobId: string, event: Omit<JobEvent, "apiVersion" | "sequence" | "occurredAt">): Promise<JobEvent | null> {
    const job = await this.get(jobId);
    if (!job) return null;
    const full: JobEvent = {
      apiVersion: "1",
      sequence: job.sequence + 1,
      occurredAt: new Date().toISOString(),
      ...event,
    };
    const { error } = await this.db.from("job_events").insert({
      job_id: jobId,
      sequence: full.sequence,
      type: full.type,
      state: full.state,
      stage: full.stage,
      payload: {
        message: full.message,
        artifactId: full.artifactId,
        errorCode: full.errorCode,
        retryable: full.retryable,
        warningCount: full.warningCount,
        progress: full.progress,
      },
    });
    if (error) return null;
    return full;
  }

  async eventsSince(jobId: string, afterSequence: number, limit = 100): Promise<JobEvent[]> {
    const { data } = await this.db
      .from("job_events")
      .select("*")
      .eq("job_id", jobId)
      .gt("sequence", afterSequence)
      .order("sequence", { ascending: true })
      .limit(limit);
    return (data ?? []).map((row) => ({
      apiVersion: "1" as const,
      sequence: row.sequence as number,
      jobId,
      type: row.type,
      state: row.state,
      stage: row.stage,
      occurredAt: row.created_at,
      ...(row.payload ?? {}),
    }));
  }
}

export { toSnapshot };
export type { ConversionJob, JobSnapshot };
