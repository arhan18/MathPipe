import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  canTransition,
  isTerminal,
  validateCreateInput,
  toSnapshot,
  InMemoryJobStore,
} from "../dist/index.js";

describe("job state machine", () => {
  it("accepts the happy path", () => {
    assert.equal(canTransition("queued", "analyzing"), true);
    assert.equal(canTransition("analyzing", "processing"), true);
    assert.equal(canTransition("processing", "reconstructing"), true);
    assert.equal(canTransition("reconstructing", "verifying"), true);
    assert.equal(canTransition("verifying", "finalizing"), true);
    assert.equal(canTransition("finalizing", "completed"), true);
  });

  it("allows repair loop and warnings", () => {
    assert.equal(canTransition("verifying", "repairing"), true);
    assert.equal(canTransition("repairing", "verifying"), true);
    assert.equal(canTransition("finalizing", "completed_with_warnings"), true);
  });

  it("rejects skips and backward moves", () => {
    assert.equal(canTransition("queued", "completed"), false);
    assert.equal(canTransition("verifying", "queued"), false);
    assert.equal(canTransition("completed", "failed"), false);
  });

  it("marks terminal states", () => {
    for (const s of ["completed", "completed_with_warnings", "failed", "cancelled", "expired"]) {
      assert.equal(isTerminal(s), true);
    }
    assert.equal(isTerminal("verifying"), false);
  });
});

describe("create validation", () => {
  it("accepts a well-formed request", () => {
    const r = validateCreateInput({ id: "j1", userId: "u", sourceFileId: "f", mode: "verified", idempotencyKey: "k" });
    assert.equal(r.ok, true);
  });

  it("rejects bad mode, missing key, bad page range, missing id", () => {
    assert.equal(validateCreateInput({ id: "j", userId: "u", sourceFileId: "f", mode: "x", idempotencyKey: "k" }).ok, false);
    assert.equal(validateCreateInput({ id: "j", userId: "u", sourceFileId: "f", mode: "standard" }).ok, false);
    assert.equal(validateCreateInput({ userId: "u", sourceFileId: "f", mode: "standard", idempotencyKey: "k" }).ok, false);
    const bad = validateCreateInput({ id: "j", userId: "u", sourceFileId: "f", mode: "standard", idempotencyKey: "k", pageRange: "1-10; rm -rf" });
    assert.equal(bad.ok, false);
    if (!bad.ok) assert.equal(bad.code, "INVALID_INPUT");
  });
});

describe("in-memory store", () => {
  it("creates once per idempotency key", async () => {
    const store = new InMemoryJobStore();
    const input = { id: "j1", userId: "u", sourceFileId: "f", mode: "standard", idempotencyKey: "k1" };
    const a = await store.create(input);
    const b = await store.create(input);
    assert.equal(a.replayed, false);
    assert.equal(b.replayed, true);
    assert.equal(a.job.id, b.job.id);
  });

  it("starts uploaded and walks the entry chain", async () => {
    const store = new InMemoryJobStore();
    const { job } = await store.create({ id: "j2", userId: "u", sourceFileId: "f", mode: "standard", idempotencyKey: "k2" });
    assert.equal(job.state, "uploaded");
    assert.equal(job.id, "j2");
    assert.equal(await store.transition(job.id, "completed"), null);
    assert.equal(await store.transition(job.id, "analyzing"), null);
    const v = await store.transition(job.id, "validating");
    assert.notEqual(v, null);
    const moved = await store.transition(job.id, "queued");
    assert.notEqual(moved, null);
    const snap = toSnapshot(moved);
    assert.equal(snap.state, "queued");
    assert.equal(snap.progress.known, false);
  });

  it("records bounded event logs", async () => {
    const store = new InMemoryJobStore();
    const { job } = await store.create({ id: "j3", userId: "u", sourceFileId: "f", mode: "standard", idempotencyKey: "k3" });
    await store.appendEvent(job.id, { jobId: job.id, type: "job.stage", state: "queued", stage: "queued", progress: { known: false, completed: null, total: null } });
    const events = await store.eventsSince(job.id, 0);
    assert.equal(events.length, 1);
    assert.equal(events[0].apiVersion, "1");
    assert.equal((await store.eventsSince(job.id, 99)).length, 0);
  });
});
