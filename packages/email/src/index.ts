/**
 * @mathpipe/email — transactional email (§27).
 *
 * Versioned template registry + provider seam. Conversion completion never
 * blocks on email delivery: callers enqueue and continue. The Resend adapter
 * activates with RESEND_API_KEY; until then the log adapter records sends
 * for tests and local development.
 */

export type EmailKind =
  | "WELCOME"
  | "CONVERSION_COMPLETED"
  | "CONVERSION_FAILED"
  | "USAGE_WARNING"
  | "SUBSCRIPTION_STARTED"
  | "SUBSCRIPTION_RENEWED"
  | "PAYMENT_FAILED";

export interface EmailTemplate {
  kind: EmailKind;
  version: number;
  subject: (vars: Record<string, string>) => string;
  text: (vars: Record<string, string>) => string;
}

const esc = (s: string) => s;

export const TEMPLATES: Record<EmailKind, EmailTemplate> = {
  WELCOME: {
    kind: "WELCOME",
    version: 1,
    subject: () => "Welcome to MathPipe",
    text: (v) => `Hi ${esc(v.name ?? "there")},\n\nYour account is ready. Convert your first math PDF at ${esc(v.appUrl ?? "MathPipe")}.\n\nFree plan: 10 pages/month.`,
  },
  CONVERSION_COMPLETED: {
    kind: "CONVERSION_COMPLETED",
    version: 1,
    subject: (v) => `Your Word document is ready (${esc(v.pages ?? "?")} pages)`,
    text: (v) => `Good news — "${esc(v.filename ?? "your file")}" converted successfully.\n\nEquations: ${esc(v.equations ?? "?")} · Tables: ${esc(v.tables ?? "?")} · Figures: ${esc(v.figures ?? "?")}\nDownload it from your history: ${esc(v.appUrl ?? "MathPipe")}/dashboard/history`,
  },
  CONVERSION_FAILED: {
    kind: "CONVERSION_FAILED",
    version: 1,
    subject: () => "Your conversion could not complete",
    text: (v) => `We couldn't complete "${esc(v.filename ?? "your file")}".\n\n${esc(v.reason ?? "Please try again or use another PDF.")}\n\nNo pages were deducted for failed infrastructure errors.`,
  },
  USAGE_WARNING: {
    kind: "USAGE_WARNING",
    version: 1,
    subject: () => "You're almost out of conversion pages",
    text: (v) => `You have ${esc(v.remaining ?? "?")} conversion pages left this month (resets ${esc(v.resetDate ?? "soon")}).\n\nUpgrade to keep converting: ${esc(v.appUrl ?? "MathPipe")}/pricing`,
  },
  SUBSCRIPTION_STARTED: {
    kind: "SUBSCRIPTION_STARTED",
    version: 1,
    subject: (v) => `You're on MathPipe ${esc(v.plan ?? "Pro")}`,
    text: (v) => `Your ${esc(v.plan ?? "Pro")} subscription is active.\n\nManage it anytime: ${esc(v.appUrl ?? "MathPipe")}/dashboard/billing`,
  },
  SUBSCRIPTION_RENEWED: {
    kind: "SUBSCRIPTION_RENEWED",
    version: 1,
    subject: () => "Subscription renewed",
    text: (v) => `Your MathPipe subscription renewed. Usage allowances reset for the new period.`,
  },
  PAYMENT_FAILED: {
    kind: "PAYMENT_FAILED",
    version: 1,
    subject: () => "Payment failed — action needed",
    text: (v) => `We couldn't charge your payment method. Update it here: ${esc(v.appUrl ?? "MathPipe")}/dashboard/billing\n\nYour current benefits continue until the end of the paid period.`,
  },
};

export interface OutboundEmail {
  to: string;
  kind: EmailKind;
  vars: Record<string, string>;
}

export interface SentEmail extends OutboundEmail {
  subject: string;
  text: string;
  templateVersion: number;
  provider: string;
  id: string;
}

export function renderEmail(email: OutboundEmail): SentEmail {
  const template = TEMPLATES[email.kind];
  return {
    ...email,
    subject: template.subject(email.vars),
    text: template.text(email.vars),
    templateVersion: template.version,
    provider: "render",
    id: `preview_${Date.now().toString(36)}`,
  };
}

export interface EmailProvider {
  name: string;
  send(email: OutboundEmail): Promise<SentEmail>;
}

/** Log adapter: records sends, delivers nothing. Tests + local dev only. */
export class LogEmailProvider implements EmailProvider {
  name = "log";
  readonly outbox: SentEmail[] = [];
  async send(email: OutboundEmail): Promise<SentEmail> {
    const rendered = { ...renderEmail(email), provider: this.name, id: `log_${this.outbox.length + 1}` };
    this.outbox.push(rendered);
    return rendered;
  }
}

/** Resend adapter. Throws a typed error without RESEND_API_KEY. */
export class ResendEmailProvider implements EmailProvider {
  name = "resend";
  constructor(
    private apiKey = process.env.RESEND_API_KEY ?? "",
    private from = process.env.RESEND_FROM ?? "MathPipe <noreply@mathpipe.app>",
  ) {}
  async send(email: OutboundEmail): Promise<SentEmail> {
    if (!this.apiKey) throw new Error("RESEND_API_KEY is not configured.");
    const rendered = renderEmail(email);
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${this.apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: this.from, to: email.to, subject: rendered.subject, text: rendered.text }),
    });
    if (!res.ok) throw new Error(`Resend send failed: ${res.status}`);
    const body = (await res.json()) as { id?: string };
    return { ...rendered, provider: this.name, id: body.id ?? `resend_${Date.now().toString(36)}` };
  }
}
