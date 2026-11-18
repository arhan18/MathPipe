/**
 * @mathpipe/observability — minimal request logging (Phase 2).
 *
 * Console-structured logs with propagated IDs. The Phase 14 OpenTelemetry /
 * Sentry stack replaces the sink, not the call sites: keep using
 * startRequest() / logStage() and never log document content, tokens or keys.
 */

export interface RequestContext {
  requestId: string;
  jobId?: string;
  userId?: string;
  startedAt: number;
}

export function startRequest(requestId: string, extra?: Pick<RequestContext, "jobId" | "userId">): RequestContext {
  return { requestId, startedAt: Date.now(), ...extra };
}

export function logEvent(ctx: RequestContext, event: string, fields?: Record<string, string | number | boolean>): void {
  const line = JSON.stringify({
    ts: new Date().toISOString(),
    requestId: ctx.requestId,
    ...(ctx.jobId ? { jobId: ctx.jobId } : {}),
    ...(ctx.userId ? { userId: ctx.userId } : {}),
    event,
    durationMs: Date.now() - ctx.startedAt,
    ...fields,
  });
  // eslint-disable-next-line no-console
  console.log(line);
}
