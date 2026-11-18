/**
 * Token-bucket rate limiter (§51.1). Server-side enforcement.
 *
 * Single-instance in-memory implementation for scaffold/dev. Production with
 * multiple instances must back buckets with shared coordination (edge KV /
 * Redis) — the interface stays identical.
 */

export type RouteGroup = "auth" | "upload" | "jobs" | "poll" | "download" | "feedback";
export type AccountTier = "anonymous" | "free" | "pro" | "power" | "business";

interface BucketSpec {
  capacity: number;
  perMinute: number;
}

/** [anonymous, free, pro, power, business] — capacity / refill-per-minute. */
const TABLE: Record<RouteGroup, [BucketSpec, BucketSpec, BucketSpec, BucketSpec, BucketSpec]> = {
  auth: [
    { capacity: 10, perMinute: 10 },
    { capacity: 10, perMinute: 10 },
    { capacity: 10, perMinute: 10 },
    { capacity: 10, perMinute: 10 },
    { capacity: 20, perMinute: 20 },
  ],
  upload: [
    { capacity: 5, perMinute: 3 },
    { capacity: 10, perMinute: 5 },
    { capacity: 10, perMinute: 20 },
    { capacity: 20, perMinute: 40 },
    { capacity: 40, perMinute: 60 },
  ],
  jobs: [
    { capacity: 2, perMinute: 2 },
    { capacity: 5, perMinute: 5 },
    { capacity: 20, perMinute: 20 },
    { capacity: 40, perMinute: 40 },
    { capacity: 60, perMinute: 60 },
  ],
  poll: [
    { capacity: 30, perMinute: 30 },
    { capacity: 30, perMinute: 30 },
    { capacity: 60, perMinute: 60 },
    { capacity: 120, perMinute: 120 },
    { capacity: 240, perMinute: 240 },
  ],
  download: [
    { capacity: 30, perMinute: 30 },
    { capacity: 60, perMinute: 60 },
    { capacity: 120, perMinute: 120 },
    { capacity: 240, perMinute: 240 },
    { capacity: 480, perMinute: 480 },
  ],
  feedback: [
    { capacity: 5, perMinute: 5 },
    { capacity: 10, perMinute: 10 },
    { capacity: 20, perMinute: 20 },
    { capacity: 20, perMinute: 20 },
    { capacity: 50, perMinute: 50 },
  ],
};

const TIER_INDEX: Record<AccountTier, number> = {
  anonymous: 0,
  free: 1,
  pro: 2,
  power: 3,
  business: 4,
};

interface Bucket {
  tokens: number;
  updatedAt: number;
}

export interface LimitResult {
  allowed: boolean;
  retryAfterSeconds: number;
}

export class TokenBucketLimiter {
  private buckets = new Map<string, Bucket>();
  private now: () => number;

  constructor(now?: () => number) {
    this.now = now ?? Date.now;
  }

  consume(identity: string, route: RouteGroup, tier: AccountTier): LimitResult {
    const spec = TABLE[route][TIER_INDEX[tier]];
    const key = `${identity}:${route}:${tier}`;
    const t = this.now();
    let bucket = this.buckets.get(key);
    if (!bucket) {
      bucket = { tokens: spec.capacity, updatedAt: t };
      this.buckets.set(key, bucket);
    }
    const elapsedMin = (t - bucket.updatedAt) / 60000;
    bucket.tokens = Math.min(spec.capacity, bucket.tokens + elapsedMin * spec.perMinute);
    bucket.updatedAt = t;
    if (bucket.tokens >= 1) {
      bucket.tokens -= 1;
      return { allowed: true, retryAfterSeconds: 0 };
    }
    const deficit = 1 - bucket.tokens;
    const retryAfterSeconds = Math.max(1, Math.ceil((deficit / spec.perMinute) * 60));
    return { allowed: false, retryAfterSeconds };
  }

  /** Test/ops introspection. */
  size(): number {
    return this.buckets.size;
  }
}
