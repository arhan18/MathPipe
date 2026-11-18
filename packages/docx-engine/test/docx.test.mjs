import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { checkOmmlSnippet, checkDocxBytes } from "../dist/index.js";

const dir = join(dirname(fileURLToPath(import.meta.url)), "fixtures");

describe("docx-engine", () => {
  it("all OMML corpus snippets carry required constructs", () => {
    const files = readdirSync(dir).filter((f) => f.endsWith(".xml") && !f.startsWith("._"));
    assert.ok(files.length >= 8);
    for (const f of files) {
      const name = f.replace(".xml", "");
      const xml = readFileSync(join(dir, f), "utf8");
      const check = checkOmmlSnippet(name, xml);
      assert.deepEqual(check.missing, [], `${name}: missing ${check.missing}`);
    }
  });

  it("sample DOCX passes container integrity", () => {
    const raw = new Uint8Array(readFileSync(join(dir, "algebra-worksheet.docx")));
    assert.deepEqual(checkDocxBytes(raw), { ok: true });
  });

  it("rejects non-DOCX bytes", () => {
    assert.equal(checkDocxBytes(new Uint8Array([1, 2, 3, 4])).ok, false);
  });
});
