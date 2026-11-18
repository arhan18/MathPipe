/**
 * @mathpipe/math-engine — client/shared math utilities (§11.3–§11.4, §60.1).
 *
 * Mirrors the Python recognizer's normalization + routing policy so the web
 * layer applies identical rules. Recognition itself runs in the processor;
 * this package never guesses equations.
 */

const COMMAND_ALIASES: Record<string, string> = {
  "\\dfrac": "\\frac",
  "\\tfrac": "\\frac",
  "\\cfrac": "\\frac",
  "\\cdot": "\\times",
  "\\ast": "\\times",
  "\\bullet": "\\times",
  "\\ldots": "\\dots",
  "\\longrightarrow": "\\to",
  "\\Longrightarrow": "\\Rightarrow",
  "\\le": "\\leq",
  "\\ge": "\\geq",
  "\\empty": "\\emptyset",
  "\\phi": "\\varphi",
  "\\epsilon": "\\varepsilon",
};

const UNICODE_TO_LATEX: Record<string, string> = {
  "×": "\\times",
  "÷": "\\div",
  "±": "\\pm",
  "√": "\\sqrt",
  "∞": "\\infty",
  "∂": "\\partial",
  "∇": "\\nabla",
  "∑": "\\sum",
  "∏": "\\prod",
  "∫": "\\int",
  "≠": "\\neq",
  "≤": "\\leq",
  "≥": "\\geq",
  "≈": "\\approx",
  "≡": "\\equiv",
  "∈": "\\in",
  "→": "\\to",
  "α": "\\alpha",
  "β": "\\beta",
  "π": "\\pi",
  "σ": "\\sigma",
  "φ": "\\varphi",
  "ω": "\\omega",
  "Δ": "\\Delta",
  "Σ": "\\Sigma",
  "Ω": "\\Omega",
};

export function normalizeLatex(latex: string): string {
  let s = latex.replace(/\s+/g, " ").trim();
  for (const [alias, canonical] of Object.entries(COMMAND_ALIASES)) {
    s = s.split(alias).join(canonical);
  }
  for (const [uni, cmd] of Object.entries(UNICODE_TO_LATEX)) {
    s = s.split(uni).join(cmd);
  }
  s = s.replace(/\\left\s*([([{|\]])/g, "$1").replace(/\\right\s*([)\]}|])/g, "$1");
  return s;
}

export type RoutingAction = "accept" | "secondary_check" | "fallback_recognizer" | "escalate";

export interface Routing {
  action: RoutingAction;
  reason: string;
}

/** Confidence routing policy (§60.1). Thresholds calibrate on the golden corpus. */
export function routeConfidence(confidence: number): Routing {
  if (confidence >= 0.95) return { action: "accept", reason: "high confidence after structural validation" };
  if (confidence >= 0.8) return { action: "secondary_check", reason: "lightweight secondary validation" };
  if (confidence >= 0.6) return { action: "fallback_recognizer", reason: "approved fallback recognizer or stronger model" };
  return { action: "escalate", reason: "do not silently trust; image fallback + warning metadata" };
}

export interface NumberedEquation {
  body: string;
  number: string | null;
}

/** Split a trailing equation number "(4)" into linked metadata. */
export function splitEquationNumber(text: string): NumberedEquation {
  const stripped = text.trim();
  const m = stripped.match(/^(.*?)[([{](\d+[a-z]?)[)\]}]?\s*$/);
  if (!m || m[1].trim().length < 2) return { body: stripped, number: null };
  return { body: m[1].trim(), number: m[2] };
}

/** Structural sanity for normalized LaTeX: balanced delimiters. */
export function hasBalancedDelimiters(latex: string): boolean {
  const pairs: Record<string, string> = { "(": ")", "[": "]", "{": "}" };
  const stack: string[] = [];
  for (const ch of latex) {
    if (pairs[ch]) stack.push(pairs[ch]);
    else if (Object.values(pairs).includes(ch)) {
      if (stack.pop() !== ch) return false;
    }
  }
  return stack.length === 0;
}
