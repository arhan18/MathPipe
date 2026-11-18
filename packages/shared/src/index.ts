/**
 * @mathpipe/shared — API conventions (§43.1): versioning, error envelope,
 * request IDs. No business logic lives here.
 */

export const API_VERSION = "1" as const;

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    requestId: string;
    details?: Record<string, unknown>;
  };
}

export function errorBody(code: string, message: string, requestId: string, details?: Record<string, unknown>): ApiErrorBody {
  return { error: { code, message, requestId, ...(details ? { details } : {}) } };
}

/** HTTP status for a machine-readable error code. Never infer state from status alone. */
export function statusFor(code: string): number {
  switch (code) {
    case "INVALID_INPUT":
      return 400;
    case "RATE_LIMITED":
    case "QUOTA_EXCEEDED":
      return 429;
    case "NOT_FOUND":
      return 404;
    case "CONFLICT":
      return 409;
    case "AUTH_NOT_CONFIGURED":
      return 503;
    case "TEMPORARY_PROVIDER_ERROR":
      return 502;
    default:
      return 500;
  }
}

export function newRequestId(): string {
  return `req_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

export { TokenBucketLimiter } from "./rate-limit.js";
export type { RouteGroup, AccountTier, LimitResult } from "./rate-limit.js";
