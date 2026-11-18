/**
 * @mathpipe/verification — verification report contracts (§18).
 *
 * Mirrors the Python verifier's report shape so the web layer can validate,
 * display and persist results. Detection/repair run in the processor; this
 * package types and validates their output.
 */

export type VerificationMode = "standard" | "verified";
export type IssueSeverity = "critical" | "warning";
export type IssueCategory =
  | "missing_text"
  | "equation_structure"
  | "equation_count"
  | "table"
  | "figure"
  | "reading_order";
export type VerificationStatus = "passed" | "warnings" | "failed";

export interface VerificationIssue {
  page_number: number;
  block_id: string | null;
  category: IssueCategory;
  severity: IssueSeverity;
  detail: string;
  suggested_action: string;
}

export interface VerificationSummary {
  mode: VerificationMode;
  status: VerificationStatus;
  checks: string[];
  issues: number;
  critical: number;
  repaired: number;
  escalated: number;
  verified_pages: number;
}

const KNOWN_CHECKS = new Set([
  "text_presence",
  "equation_structure",
  "docx_consistency",
  "bounded_repair",
  "ai_region_review",
]);

/** Validate a processor-produced summary before display or persistence. */
export function validateSummary(summary: unknown): string[] {
  const problems: string[] = [];
  if (typeof summary !== "object" || summary === null) return ["summary must be an object"];
  const s = summary as Record<string, unknown>;
  if (s.mode !== "standard" && s.mode !== "verified") problems.push("mode must be standard|verified");
  if (!["passed", "warnings", "failed"].includes(s.status as string)) problems.push("invalid status");
  if (!Array.isArray(s.checks)) problems.push("checks must be an array");
  else for (const c of s.checks) if (!KNOWN_CHECKS.has(c as string)) problems.push(`unknown check: ${c}`);
  for (const k of ["issues", "critical", "repaired", "escalated", "verified_pages"]) {
    if (typeof s[k] !== "number" || (s[k] as number) < 0) problems.push(`${k} must be a non-negative number`);
  }
  if (typeof s.critical === "number" && typeof s.issues === "number" && (s.critical as number) > (s.issues as number)) {
    problems.push("critical cannot exceed issues");
  }
  return problems;
}

/** User-facing headline for a verification outcome. Never invents certainty. */
export function headlineFor(summary: VerificationSummary): string {
  if (summary.status === "passed") return "Verified successfully";
  if (summary.status === "warnings") {
    return `Completed with ${summary.issues} region${summary.issues === 1 ? "" : "s"} to review`;
  }
  return "Verification found critical issues";
}
