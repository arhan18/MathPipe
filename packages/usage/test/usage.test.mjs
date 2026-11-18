import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { deriveBalance, authorizeConversion, authorizeFileSize } from "../dist/index.js";

/** @type {import("../dist/index.js").PlanQuotas} */
const FREE = {
  planId: "free",
  conversionPages: 10,
  verifiedPages: 0,
  maxFileMb: 25,
  maxPagesPerJob: 25,
  maxConcurrentJobs: 1,
};

describe("usage balances", () => {
  it("derives remaining from the event trail", () => {
    const b = deriveBalance(FREE, [
      { kind: "conversion_page_consumed", quantity: 4 },
      { kind: "credit_granted", quantity: 1 },
    ]);
    assert.equal(b.conversionUsed, 3);
    assert.equal(b.conversionRemaining, 7);
  });

  it("never goes negative", () => {
    const b = deriveBalance(FREE, [{ kind: "credit_granted", quantity: 99 }]);
    assert.equal(b.conversionUsed, 0);
    assert.equal(b.conversionRemaining, 10);
  });
});

describe("quota authorization", () => {
  it("allows a fitting standard conversion", () => {
    const b = deriveBalance(FREE, []);
    assert.equal(authorizeConversion(FREE, b, 8, "standard").ok, true);
  });

  it("blocks over-quota, over-limit, and empty jobs", () => {
    const b = deriveBalance(FREE, [{ kind: "conversion_page_consumed", quantity: 6 }]);
    const over = authorizeConversion(FREE, b, 8, "standard");
    assert.equal(over.ok, false);
    if (!over.ok) assert.equal(over.code, "QUOTA_EXCEEDED");
    assert.equal(authorizeConversion(FREE, b, 30, "standard").ok, false);
    assert.equal(authorizeConversion(FREE, b, 0, "standard").ok, false);
  });

  it("blocks verified mode without allowance", () => {
    const b = deriveBalance(FREE, []);
    const r = authorizeConversion(FREE, b, 5, "verified");
    assert.equal(r.ok, false);
    if (!r.ok) assert.equal(r.code, "QUOTA_EXCEEDED");
  });

  it("blocks oversized files", () => {
    assert.equal(authorizeFileSize(FREE, 10).ok, true);
    const r = authorizeFileSize(FREE, 40);
    assert.equal(r.ok, false);
    if (!r.ok) assert.equal(r.code, "PAGE_LIMIT_EXCEEDED");
  });
});
