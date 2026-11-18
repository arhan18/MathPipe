/**
 * @mathpipe/jobs — conversion job state machine, contracts and store seam.
 *
 * Canonical states per architecture §21 + §60.0D and user-flow.md.
 * Phase 2 ships an in-memory store behind the JobStore interface;
 * Phase 3 provides the Supabase-backed implementation. No caller may
 * depend on InMemoryJobStore outside tests and local scaffolding.
 */

export type ConversionMode = "standard" | "verified";

export type JobState =
  | "uploaded"
  | "validating"
  | "queued"
  | "analyzing"
  | "processing"
  | "reconstructing"
  | "verifying"
  | "repairing"
  | "finalizing"
  | "completed"
  | "completed_with_warnings"
  | "failed"
  | "cancelled"
  | "expired";

const TERMINAL: ReadonlySet<JobState> = new Set([
  "completed",
  "completed_with_warnings",
  "failed",
  "cancelled",
  "expired",
]);

export function isTerminal(state: JobState): boolean {
  return TERMINAL.has(state);
}

/** Legal transitions. Anything else is a no-op rejection (never silent). */
const TRANSITIONS: Record<JobState, readonly JobState[]> = {
  uploaded: ["validating", "failed", "cancelled"],
  validating: ["queued", "failed", "cancelled"],
  queued: ["analyzing", "failed", "cancelled"],
  analyzing: ["processing", "failed", "cancelled"],
  processing: ["reconstructing", "failed", "cancelled"],
  reconstructing: ["verifying", "finalizing", "failed", "cancelled"],
  verifying: ["repairing", "finalizing", "failed", "cancelled"],
  repairing: ["verifying", "finalizing", "failed", "cancelled"],
  finalizing: ["completed", "completed_with_warnings", "failed", "cancelled"],
  completed: [],
  completed_with_warnings: [],
  failed: [],
  cancelled: [],
  expired: [],
};

export function canTransition(from: JobState, to: JobState): boolean {
  return TRANSITIONS[from]?.includes(to) ?? false;
}

/** Machine-readable error codes (§30 + transport). */
export type ErrorCode =
  | "FILE_INVALID"
  | "FILE_TOO_LARGE"
  | "PAGE_LIMIT_EXCEEDED"
  | "QUOTA_EXCEEDED"
  | "UNSUPPORTED_DOCUMENT"
  | "PROCESSING_FAILED"
  | "TEMPORARY_PROVIDER_ERROR"
  | "VERIFICATION_FAILED"
  | "OUTPUT_GENERATION_FAILED"
  | "AUTH_NOT_CONFIGURED"
  | "RATE_LIMITED"
  | "NOT_FOUND"
  | "INVALID_INPUT"
  | "CONFLICT"
  | "INTERNAL";

export interface ConversionJob {
  id: string;
  userId: string;
  sourceFileId: string;
  mode: ConversionMode;
  pageRange: string | null;
  state: JobState;
  errorCode: ErrorCode | null;
  retryable: boolean;
  warningCount: number;
  artifactId: string | null;
  sequence: number;
  createdAt: string;
  updatedAt: string;
}

export interface JobProgress {
  known: boolean;
  completed: number | null;
  total: number | null;
}

/** Authoritative snapshot served by GET /api/v1/jobs/[id] and SSE (§21.1, §28.1). */
export interface JobSnapshot {
  id: string;
  state: JobState;
  stage: string;
  sequence: number;
  updatedAt: string;
  progress: JobProgress;
  warningCount: number;
  errorCode: ErrorCode | null;
}

export type JobEventType =
  | "job.snapshot"
  | "job.stage"
  | "job.warning"
  | "job.completed"
  | "job.failed"
  | "heartbeat";

export interface JobEvent {
  apiVersion: "1";
  sequence: number;
  jobId: string;
  type: JobEventType;
  occurredAt: string;
  state: JobState;
  stage: string;
  progress: JobProgress;
  message?: string;
  artifactId?: string;
  errorCode?: ErrorCode;
  retryable?: boolean;
  warningCount?: number;
}

export function toSnapshot(job: ConversionJob): JobSnapshot {
  return {
    id: job.id,
    state: job.state,
    stage: job.state,
    sequence: job.sequence,
    updatedAt: job.updatedAt,
    progress: { known: false, completed: null, total: null },
    warningCount: job.warningCount,
    errorCode: job.errorCode,
  };
}

export interface CreateJobInput {
  /** Caller-assigned ID. The route generates it BEFORE upload so the storage
   *  key and the job row share one ID (the DB must not mint a second one). */
  id: string;
  userId: string;
  sourceFileId: string;
  mode: ConversionMode;
  pageRange?: string | null;
  idempotencyKey: string;
}

export function validateCreateInput(input: Partial<CreateJobInput>): { ok: true; value: CreateJobInput } | { ok: false; code: ErrorCode; message: string } {
  if (!input.id) return { ok: false, code: "INVALID_INPUT", message: "id is required." };
  if (!input.userId) return { ok: false, code: "INVALID_INPUT", message: "userId is required." };
  if (!input.sourceFileId) return { ok: false, code: "INVALID_INPUT", message: "sourceFileId is required." };
  if (input.mode !== "standard" && input.mode !== "verified") {
    return { ok: false, code: "INVALID_INPUT", message: "mode must be standard or verified." };
  }
  if (!input.idempotencyKey) return { ok: false, code: "INVALID_INPUT", message: "Idempotency-Key is required." };
  if (input.pageRange != null && !/^[0-9,\-–\s]+$/.test(input.pageRange)) {
    return { ok: false, code: "INVALID_INPUT", message: "pageRange contains unsupported characters." };
  }
  return {
    ok: true,
    value: {
      id: input.id,
      userId: input.userId,
      sourceFileId: input.sourceFileId,
      mode: input.mode,
      pageRange: input.pageRange ?? null,
      idempotencyKey: input.idempotencyKey,
    },
  };
}

/** Durable-store seam. Implementations must be safe under concurrent writers. */
export interface JobStore {
  create(input: CreateJobInput): Promise<{ job: ConversionJob; replayed: boolean }>;
  get(jobId: string): Promise<ConversionJob | null>;
  transition(jobId: string, to: JobState, patch?: Partial<Pick<ConversionJob, "errorCode" | "retryable" | "warningCount" | "artifactId">>): Promise<ConversionJob | null>;
  appendEvent(jobId: string, event: Omit<JobEvent, "apiVersion" | "sequence" | "occurredAt">): Promise<JobEvent | null>;
  eventsSince(jobId: string, afterSequence: number, limit?: number): Promise<JobEvent[]>;
}

function now() {
  return new Date().toISOString();
}

function uid(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * In-memory store. Scaffold seam only — single instance, no persistence.
 * Production traffic must use the Phase 3 Supabase implementation.
 */
export class InMemoryJobStore implements JobStore {
  private jobs = new Map<string, ConversionJob>();
  private byIdempotency = new Map<string, string>();
  private events = new Map<string, JobEvent[]>();

  async create(input: CreateJobInput): Promise<{ job: ConversionJob; replayed: boolean }> {
    const existingId = this.byIdempotency.get(input.idempotencyKey);
    if (existingId) {
      const existing = this.jobs.get(existingId);
      if (existing) return { job: existing, replayed: true };
    }
    const job: ConversionJob = {
      id: input.id,
      userId: input.userId,
      sourceFileId: input.sourceFileId,
      mode: input.mode,
      pageRange: input.pageRange ?? null,
      state: "uploaded",
      errorCode: null,
      retryable: false,
      warningCount: 0,
      artifactId: null,
      sequence: 0,
      createdAt: now(),
      updatedAt: now(),
    };
    this.jobs.set(job.id, job);
    this.byIdempotency.set(input.idempotencyKey, job.id);
    this.events.set(job.id, []);
    return { job, replayed: false };
  }

  async get(jobId: string): Promise<ConversionJob | null> {
    return this.jobs.get(jobId) ?? null;
  }

  async transition(
    jobId: string,
    to: JobState,
    patch?: Partial<Pick<ConversionJob, "errorCode" | "retryable" | "warningCount" | "artifactId">>,
  ): Promise<ConversionJob | null> {
    const job = this.jobs.get(jobId);
    if (!job) return null;
    if (!canTransition(job.state, to)) return null;
    const next: ConversionJob = {
      ...job,
      ...patch,
      state: to,
      sequence: job.sequence + 1,
      updatedAt: now(),
    };
    this.jobs.set(jobId, next);
    return next;
  }

  async appendEvent(jobId: string, event: Omit<JobEvent, "apiVersion" | "sequence" | "occurredAt">): Promise<JobEvent | null> {
    const job = this.jobs.get(jobId);
    if (!job) return null;
    const log = this.events.get(jobId) ?? [];
    const full: JobEvent = {
      apiVersion: "1",
      sequence: job.sequence + 1,
      occurredAt: now(),
      ...event,
    };
    log.push(full);
    if (log.length > 200) log.splice(0, log.length - 200);
    this.events.set(jobId, log);
    return full;
  }

  async eventsSince(jobId: string, afterSequence: number, limit = 100): Promise<JobEvent[]> {
    const log = this.events.get(jobId) ?? [];
    return log.filter((e) => e.sequence > afterSequence).slice(0, limit);
  }
}
