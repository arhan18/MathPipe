import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { routeVerification, createBudget, charge, StubProvider } from "../dist/index.js";

const ctx = (over = {}) => ({
  task: "verify",
  plan: "pro",
  budgetRemaining: 0.5,
  freeAllocationRemaining: 10,
  ...over,
});

describe("ai-router", () => {
  it("skips AI for high confidence", () => {
    const d = routeVerification(0.98, ctx({ freeAllocationRemaining: 0, budgetRemaining: 0 }));
    assert.equal(d.provider, "none");
    assert.equal(d.stop, false);
  });

  it("prefers free allocation, then cheapest, then stops", () => {
    assert.equal(routeVerification(0.8, ctx()).provider, "cloudflare");
    const paid = routeVerification(0.8, ctx({ freeAllocationRemaining: 0 }));
    assert.equal(paid.provider, "fallback");
    assert.ok(paid.estimatedCost > 0);
    const broke = routeVerification(0.8, ctx({ freeAllocationRemaining: 0, budgetRemaining: 0.001 }));
    assert.equal(broke.stop, true);
  });

  it("never exceeds the job budget", () => {
    const b = createBudget("pro");
    assert.equal(charge(b, 0.4), true);
    assert.equal(charge(b, 0.2), false);
    assert.equal(b.spent, 0.4);
  });

  it("free plans get zero AI budget", () => {
    assert.equal(createBudget("free").maxSpend, 0);
  });

  it("stub provider answers without billing", async () => {
    const p = new StubProvider();
    assert.equal(await p.available(), true);
    const v = await p.verify({ jobId: "j", pageNumber: 1, blockId: "b", kind: "equation", payload: "x^2", confidence: 0.9 });
    assert.equal(v.match, true);
    assert.equal(v.costCharged, 0);
  });
});
