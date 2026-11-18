import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { TEMPLATES, renderEmail, LogEmailProvider, ResendEmailProvider } from "../dist/index.js";

describe("email", () => {
  it("renders every template without placeholders leaking", () => {
    const vars = { name: "Asha", appUrl: "https://x.test", filename: "ch3.pdf", pages: "12", equations: "40", tables: "3", figures: "5", remaining: "8", resetDate: "Nov 1", plan: "Pro", reason: "timeout" };
    for (const t of Object.values(TEMPLATES)) {
      const rendered = renderEmail({ to: "a@x.test", kind: t.kind, vars });
      assert.ok(rendered.subject.length > 0);
      assert.ok(rendered.text.length > 0);
      assert.equal(rendered.templateVersion, t.version);
      assert.ok(!rendered.text.includes("undefined"));
    }
  });

  it("log provider records sends", async () => {
    const p = new LogEmailProvider();
    const sent = await p.send({ to: "a@x.test", kind: "WELCOME", vars: { name: "Asha" } });
    assert.equal(p.outbox.length, 1);
    assert.equal(sent.provider, "log");
    assert.ok(sent.subject.includes("MathPipe"));
  });

  it("resend provider refuses without a key", async () => {
    const p = new ResendEmailProvider("");
    await assert.rejects(() => p.send({ to: "a@x.test", kind: "WELCOME", vars: {} }), /not configured/);
  });
});
