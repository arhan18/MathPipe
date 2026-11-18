import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  normalizeLatex,
  routeConfidence,
  splitEquationNumber,
  hasBalancedDelimiters,
} from "../dist/index.js";

describe("math-engine", () => {
  it("normalizes aliases and unicode", () => {
    assert.equal(normalizeLatex("\\dfrac{a}{b}"), "\\frac{a}{b}");
    assert.ok(normalizeLatex("a × b").includes("\\times"));
    assert.ok(normalizeLatex("√x").includes("\\sqrt"));
    assert.equal(normalizeLatex("x  +   y"), "x + y");
  });

  it("routes confidence bands", () => {
    assert.equal(routeConfidence(0.97).action, "accept");
    assert.equal(routeConfidence(0.85).action, "secondary_check");
    assert.equal(routeConfidence(0.7).action, "fallback_recognizer");
    assert.equal(routeConfidence(0.4).action, "escalate");
  });

  it("splits equation numbers", () => {
    const n = splitEquationNumber("x^2 + 1 (4)");
    assert.equal(n.number, "4");
    assert.equal(n.body, "x^2 + 1");
    assert.equal(splitEquationNumber("x + y").number, null);
  });

  it("checks delimiter balance", () => {
    assert.equal(hasBalancedDelimiters("(a + [b])"), true);
    assert.equal(hasBalancedDelimiters("(a + [b)"), false);
  });
});
