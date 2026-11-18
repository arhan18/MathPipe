/**
 * @mathpipe/ai-router — provider-agnostic AI routing (§19, §34).
 *
 * Cost-aware selective inference: deterministic checks first, free
 * allocation second, cheapest approved provider third, strong models only
 * for low-confidence regions. Every job carries a hard spend budget; the
 * router returns STOP instead of spending past it.
 */

export type AiTask = "verify" | "repair";
export type ProviderName = "cloudflare" | "fallback" | "none";

export interface AiProvider {
  name: Exclude<ProviderName, "none">;
  /** Remaining free allocation in abstract cost units for the period. */
  freeRemaining: number;
  /** Cost per verification unit (region check). */
  unitCost: number;
  available(): Promise<boolean>;
  verify(region: VerificationRegion): Promise<ProviderVerdict>;
}

export interface VerificationRegion {
  jobId: string;
  pageNumber: number;
  blockId: string;
  kind: "equation" | "text" | "table" | "figure";
  /** Canonical input, smallest sufficient (one crop / one equation). */
  payload: string;
  confidence: number;
}

export interface ProviderVerdict {
  provider: string;
  match: boolean;
  confidence: number;
  suggestedFix?: string;
  costCharged: number;
}

export interface RouteContext {
  task: AiTask;
  plan: "free" | "pro" | "power" | "business";
  budgetRemaining: number;
  freeAllocationRemaining: number;
  latencyMs?: number;
}

export interface RoutingDecision {
  provider: ProviderName;
  estimatedCost: number;
  reason: string;
  stop: boolean;
}

/** Confidence-gated selective routing (§34): high skips AI entirely. */
export function routeVerification(confidence: number, ctx: RouteContext): RoutingDecision {
  if (confidence >= 0.97) {
    return { provider: "none", estimatedCost: 0, reason: "high confidence — deterministic checks suffice", stop: false };
  }
  if (ctx.budgetRemaining <= 0) {
    return { provider: "none", estimatedCost: 0, reason: "job AI budget exhausted — flag for review, do not spend", stop: true };
  }
  if (ctx.freeAllocationRemaining > 0) {
    return { provider: "cloudflare", estimatedCost: 0, reason: "free allocation available", stop: false };
  }
  const estimate = ctx.task === "repair" ? 0.008 : 0.003;
  if (estimate > ctx.budgetRemaining) {
    return { provider: "none", estimatedCost: estimate, reason: "estimate exceeds remaining budget — flag for review", stop: true };
  }
  return { provider: "fallback", estimatedCost: estimate, reason: "cheapest approved provider", stop: false };
}

export interface JobBudget {
  maxSpend: number;
  spent: number;
  maxRepairAttemptsPerRegion: number;
  maxVerificationPasses: number;
}

export function createBudget(plan: RouteContext["plan"]): JobBudget {
  const caps = { free: 0, pro: 0.5, power: 1.5, business: 5 } as const;
  return { maxSpend: caps[plan], spent: 0, maxRepairAttemptsPerRegion: 2, maxVerificationPasses: 2 };
}

export function charge(budget: JobBudget, amount: number): boolean {
  if (budget.spent + amount > budget.maxSpend) return false;
  budget.spent = Math.round((budget.spent + amount) * 1e6) / 1e6;
  return true;
}

/** Deterministic stub provider for tests and scaffold traffic. Never billed. */
export class StubProvider implements AiProvider {
  name = "fallback" as const;
  freeRemaining = Number.POSITIVE_INFINITY;
  unitCost = 0;
  async available(): Promise<boolean> {
    return true;
  }
  async verify(region: VerificationRegion): Promise<ProviderVerdict> {
    return { provider: this.name, match: region.confidence >= 0.6, confidence: region.confidence, costCharged: 0 };
  }
}
