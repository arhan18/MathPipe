import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { verifySignature, signPayload, transitionForEvent } from "../dist/index.js";

const SECRET = "test-secret-123";
const BODY = JSON.stringify({ type: "subscription.active", data: { plan: "pro" } });

const headers = (sig, ts = String(Math.floor(Date.now() / 1000))) => ({
  id: "evt_1",
  signature: sig,
  timestamp: ts,
});

describe("billing webhooks", () => {
  it("accepts a correctly signed payload", () => {
    const ts = String(Math.floor(Date.now() / 1000));
    const sig = `v1,${signPayload(SECRET, "evt_1", ts, BODY)}`;
    assert.deepEqual(verifySignature(BODY, headers(sig, ts), SECRET), { ok: true });
  });

  it("accepts when one of several signatures matches", () => {
    const ts = String(Math.floor(Date.now() / 1000));
    const good = `v1,${signPayload(SECRET, "evt_1", ts, BODY)}`;
    assert.deepEqual(verifySignature(BODY, headers(`v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= ${good}`, ts), SECRET), { ok: true });
  });

  it("rejects tampered bodies, wrong secrets, stale timestamps", () => {
    const ts = String(Math.floor(Date.now() / 1000));
    const sig = `v1,${signPayload(SECRET, "evt_1", ts, BODY)}`;
    assert.deepEqual(verifySignature(BODY + " ", headers(sig, ts), SECRET), { ok: false, failure: "bad_signature" });
    assert.deepEqual(verifySignature(BODY, headers(sig, ts), "wrong"), { ok: false, failure: "bad_signature" });
    assert.deepEqual(verifySignature(BODY, headers(sig, "1"), SECRET), { ok: false, failure: "stale_timestamp" });
    assert.deepEqual(verifySignature(BODY, { id: "", signature: "", timestamp: "" }, SECRET), { ok: false, failure: "missing_headers" });
  });

  it("maps events to entitlements without silent upgrades", () => {
    assert.deepEqual(transitionForEvent("subscription.active", "pro"), { plan: "pro", status: "active", noop: false });
    assert.deepEqual(transitionForEvent("subscription.active", null).noop, true);
    assert.deepEqual(transitionForEvent("subscription.cancelled", "pro"), { plan: "free", status: "cancelled", noop: false });
    assert.deepEqual(transitionForEvent("payment.failed", "pro"), { plan: "free", status: "past_due", noop: false });
    assert.deepEqual(transitionForEvent("something.unknown", "pro").noop, true);
  });
});
