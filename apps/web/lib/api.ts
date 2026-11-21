import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";
import { InMemoryJobStore, type JobStore } from "@mathpipe/jobs";
import { isDbConfigured, SupabaseJobStore } from "@mathpipe/db";
import { TokenBucketLimiter, errorBody, newRequestId, statusFor, type AccountTier, type RouteGroup } from "@mathpipe/shared";
import { startRequest, logEvent } from "@mathpipe/observability";

/**
 * Shared API plumbing (§21.1, §43.1, §51.1).
 *
 * Scaffold status (Phase 2): no live Supabase project exists yet, so every
 * protected route answers 503 AUTH_NOT_CONFIGURED until env is present.
 * The session check below is the real implementation — it activates the
 * moment NEXT_PUBLIC_SUPABASE_URL + ANON_KEY are configured (Phase 3).
 * The in-memory JobStore is replaced by the Supabase implementation in
 * Phase 3; the JobStore interface (and all route logic) stays identical.
 */

const memoryStore = new InMemoryJobStore();
let supabaseStore: JobStore | null = null;

/** Supabase store when configured (Phase 3 live); in-memory scaffold otherwise. */
export function getJobStore(): JobStore {
  if (isDbConfigured()) {
    supabaseStore ??= new SupabaseJobStore();
    return supabaseStore;
  }
  return memoryStore;
}

const limiter = new TokenBucketLimiter();
export function getLimiter() {
  return limiter;
}

export function isAuthConfigured(): boolean {
  return Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
}

export interface AuthedUser {
  id: string;
  email: string | null;
}

export async function requireUser(): Promise<{ user: AuthedUser } | { response: NextResponse }> {
  if (!isAuthConfigured()) {
    return { response: apiError("AUTH_NOT_CONFIGURED", "Authentication is not configured yet.", newRequestId()) };
  }
  const jar = await cookies();
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => jar.getAll(), setAll: () => {} } },
  );
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    return { response: apiError("INVALID_INPUT", "Sign in required.", newRequestId(), undefined, 401) };
  }
  return { user: { id: data.user.id, email: data.user.email ?? null } };
}

export function apiError(code: string, message: string, requestId: string, details?: Record<string, unknown>, statusOverride?: number) {
  return NextResponse.json(errorBody(code, message, requestId, details), {
    status: statusOverride ?? statusFor(code),
  });
}

export function clientIdentity(req: Request, userId?: string): string {
  if (userId) return `user:${userId}`;
  const forwarded = req.headers.get("x-forwarded-for");
  const ip = forwarded?.split(",")[0]?.trim() || "unknown";
  return `ip:${ip}`;
}

/** Phase 3 resolves the real tier from subscriptions; scaffold assumes free for authed users. */
export function tierFor(userId?: string): AccountTier {
  return userId ? "free" : "anonymous";
}

export function checkLimit(req: Request, route: RouteGroup, userId?: string): { ok: true } | { ok: false; response: NextResponse } {
  const requestId = newRequestId();
  const result = limiter.consume(clientIdentity(req, userId), route, tierFor(userId));
  if (!result.allowed) {
    logEvent(startRequest(requestId), "rate_limited", { route });
    const res = apiError("RATE_LIMITED", "Too many requests. Please try again shortly.", requestId, {
      retryAfterSeconds: result.retryAfterSeconds,
    });
    res.headers.set("Retry-After", String(result.retryAfterSeconds));
    return { ok: false, response: res };
  }
  return { ok: true };
}
