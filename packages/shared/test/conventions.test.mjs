import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { errorBody, statusFor, newRequestId, TokenBucketLimiter } from "../dist/index.js";

describe("error envelope", () => {
  it("builds the §43.1 shape", () => {
    const body = errorBody("NOT_FOUND", "No such job.", "req_1");
    assert.equal(body.error.code, "NOT_FOUND");
    assert.equal(body.error.requestId, "req_1");
  });

  it("maps codes to statuses", () => {
    assert.equal(statusFor("INVALID_INPUT"), 400);
    assert.equal(statusFor("NOT_FOUND"), 404);
    assert.equal(statusFor("RATE_LIMITED"), 429);
    assert.equal(statusFor("QUOTA_EXCEEDED"), 429);
    assert.equal(statusFor("AUTH_NOT_CONFIGURED"), 503);
  });

  it("mints unique request ids", () => {
    assert.notEqual(newRequestId(), newRequestId());
  });
});

describe("token bucket", () => {
  it("admits within burst then rejects with retry-after", () => {
    let t = 0;
    const limiter = new TokenBucketLimiter(() => t);
    assert.equal(limiter.consume("ip", "jobs", "anonymous").allowed, true);
    assert.equal(limiter.consume("ip", "jobs", "anonymous").allowed, true);
    const third = limiter.consume("ip", "jobs", "anonymous");
    assert.equal(third.allowed, false);
    assert.ok(third.retryAfterSeconds >= 1);
  });

  it("refills over time and tiers differ", () => {
    let t = 0;
    const limiter = new TokenBucketLimiter(() => t);
    // anonymous jobs bucket: capacity 2, 2/min
    limiter.consume("a", "jobs", "anonymous");
    limiter.consume("a", "jobs", "anonymous");
    assert.equal(limiter.consume("a", "jobs", "anonymous").allowed, false);
    t += 31000; // +31s → +1 token at 2/min
    assert.equal(limiter.consume("a", "jobs", "anonymous").allowed, true);
    // pro poll bucket is roomier than anonymous
    const pro = new TokenBucketLimiter(() => 0);
    let admitted = 0;
    for (let i = 0; i < 61; i++) if (pro.consume("u", "poll", "pro").allowed) admitted++;
    assert.equal(admitted, 60);
  });

  it("isolates identities", () => {
    const limiter = new TokenBucketLimiter(() => 0);
    limiter.consume("a", "jobs", "anonymous");
    limiter.consume("a", "jobs", "anonymous");
    assert.equal(limiter.consume("b", "jobs", "anonymous").allowed, true);
  });
});
