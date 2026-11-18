import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { validateDocumentModel, readingOrderText } from "../dist/index.js";

const dir = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const load = (name) => JSON.parse(readFileSync(join(dir, name), "utf8"));

describe("document-model fixtures", () => {
  for (const name of ["algebra-two-column.json", "algebra-worksheet.json"]) {
    it(`${name} validates`, () => {
      const issues = validateDocumentModel(load(name));
      assert.deepEqual(issues, []);
    });
  }

  it("two-column fixture reads left column before right", () => {
    const texts = readingOrderText(load("algebra-two-column.json"));
    const left = texts.findIndex((t) => t.includes("Left column first"));
    const right = texts.findIndex((t) => t.includes("Right gutter") || t.includes("Right column"));
    assert.ok(left >= 0 && right >= 0 && left < right);
  });

  it("rejects malformed models", () => {
    assert.ok(validateDocumentModel(null).length > 0);
    assert.ok(validateDocumentModel({ schemaVersion: "bogus", document: { pages: [] } }).length > 0);
  });
});
