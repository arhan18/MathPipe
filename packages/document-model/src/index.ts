import { createHash } from "node:crypto";
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";

export const MATH_IR_SCHEMA_VERSION = "1.0" as const;
export const MATH_IR_SCHEMA_ID = "math-ir://schema/v1.0";

const ajv = new Ajv2020({ strict: true, allErrors: true });

let cachedValidator: ValidateFunction | undefined;

/** Compile the checked-in MathIR JSON Schema. Schema object injected by caller. */
export function compileMathIrValidator(schema: object): ValidateFunction {
  cachedValidator ??= ajv.compile(schema);
  return cachedValidator;
}

export type MathIrValidationIssue = { path: string; message: string };

/** Structural checks beyond JSON Schema: acyclicity/depth, rectangular matrices. */
export function checkMathIrStructure(root: unknown, maxDepth = 64): MathIrValidationIssue[] {
  const issues: MathIrValidationIssue[] = [];
  const seen = new Set<object>();
  const walk = (node: unknown, path: string, depth: number): void => {
    if (depth > maxDepth) {
      issues.push({ path, message: `exceeds max depth ${maxDepth}` });
      return;
    }
    if (typeof node !== "object" || node === null) {
      issues.push({ path, message: "node must be an object" });
      return;
    }
    if (seen.has(node)) {
      issues.push({ path, message: "cycle detected" });
      return;
    }
    seen.add(node);
    const n = node as Record<string, unknown>;
    if (n.type === "matrix") {
      const rows = n.rows as unknown[][];
      const widths = rows.map((r) => (Array.isArray(r) ? r.length : -1));
      if (new Set(widths).size > 1) {
        issues.push({ path, message: `ragged matrix widths: ${widths.join(",")}` });
      }
      rows.forEach((row, i) =>
        (Array.isArray(row) ? row : []).forEach((cell, j) =>
          walk(cell, `${path}.rows[${i}][${j}]`, depth + 1),
        ),
      );
    } else if (n.type === "row" || n.type === "operator") {
      const children = (n.children ?? n.arguments ?? []) as unknown[];
      children.forEach((c, i) => walk(c, `${path}.children[${i}]`, depth + 1));
    } else if (n.type === "fraction") {
      walk(n.numerator, `${path}.numerator`, depth + 1);
      walk(n.denominator, `${path}.denominator`, depth + 1);
    } else if (n.type === "superscript" || n.type === "subscript") {
      walk(n.base, `${path}.base`, depth + 1);
      walk(n.script, `${path}.script`, depth + 1);
    } else if (n.type === "root") {
      if (n.degree !== undefined) walk(n.degree, `${path}.degree`, depth + 1);
      walk(n.radicand, `${path}.radicand`, depth + 1);
    } else if (n.type === "fence" || n.type === "accent") {
      walk(n.child, `${path}.child`, depth + 1);
    } else if (n.type === "limit") {
      walk(n.base, `${path}.base`, depth + 1);
      walk(n.lower, `${path}.lower`, depth + 1);
      walk(n.upper, `${path}.upper`, depth + 1);
    } else if (n.type === "underover") {
      walk(n.base, `${path}.base`, depth + 1);
      walk(n.under, `${path}.under`, depth + 1);
      walk(n.over, `${path}.over`, depth + 1);
    } else if (n.type === "function") {
      ((n.arguments ?? []) as unknown[]).forEach((a, i) =>
        walk(a, `${path}.arguments[${i}]`, depth + 1),
      );
    } else if (n.type === "cases") {
      ((n.cases ?? []) as Array<{ expression: unknown; condition: unknown }>).forEach(
        (c, i) => {
          walk(c.expression, `${path}.cases[${i}].expression`, depth + 1);
          walk(c.condition, `${path}.cases[${i}].condition`, depth + 1);
        },
      );
    }
    seen.delete(node);
  };
  walk(root, "$.root", 0);
  return issues;
}

/** Canonical JSON serialization: stable key order, no insignificant whitespace. */
export function canonicalMathIrJson(value: unknown): string {
  const stable = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(stable);
    if (typeof v === "object" && v !== null) {
      return Object.fromEntries(
        Object.keys(v as Record<string, unknown>)
          .sort()
          .map((k) => [k, stable((v as Record<string, unknown>)[k])]),
      );
    }
    return v;
  };
  return JSON.stringify(stable(value));
}

/** Content hash for caching and provenance. */
export function hashMathIr(canonicalJson: string): string {
  return createHash("sha256").update(canonicalJson, "utf8").digest("hex");
}
