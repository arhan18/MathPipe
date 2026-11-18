import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { validateSummary, headlineFor } from "../dist/index.js";

const good = {
  mode: "verified",
  status: "passed",
  checks: ["text_presence", "equation_structure", "bounded_repair", "ai_region_review"],
  issues: 0,
  critical: 0,
  repaired: 0,
  escalated: 0,
  verified_pages: 1,
};

describe("verification", () => {
  it("accepts a well-formed summary", () => {
    assert.deepEqual(validateSummary(good), []);
    assert.equal(headlineFor(good), "Verified successfully");
  });

  it("rejects unknown checks and inconsistent counts", () => {
    assert.ok(validateSummary({ ...good, checks: ["teleport"] }).length > 0);
    assert.ok(validateSummary({ ...good, critical: 2, issues: 1 }).length > 0);
    assert.ok(validateSummary(null).length > 0);
  });

  it("words warnings honestly", () => {
    assert.equal(
      headlineFor({ ...good, status: "warnings", issues: 3 }),
      "Completed with 3 regions to review",
    );
    assert.equal(headlineFor({ ...good, status: "failed" }), "Verification found critical issues");
  });
});
