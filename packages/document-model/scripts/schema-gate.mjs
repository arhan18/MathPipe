// MathIR pre-Phase-6 gate — architecture §10.2.
// 1. schema file exists + parses + draft 2020-12
// 2. valid fixtures validate (schema + structure)
// 3. invalid fixtures are rejected
// 4. schema hash recorded
import { readFileSync, readdirSync, createWriteStream } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv from "ajv/dist/2020.js";

const here = dirname(fileURLToPath(import.meta.url));
const pkgRoot = join(here, "..");
const schemaPath = join(pkgRoot, "schemas/mathir/v1/math-ir.schema.json");
const fixturesDir = join(pkgRoot, "schemas/mathir/v1/fixtures");

const fail = (msg) => {
  console.error(`SCHEMA-GATE FAIL: ${msg}`);
  process.exit(1);
};
const pass = (msg) => console.log(`SCHEMA-GATE OK: ${msg}`);

// 1. schema file
let schemaRaw;
try {
  schemaRaw = readFileSync(schemaPath, "utf8");
} catch {
  fail(`schema file missing at ${schemaPath}`);
}
let schema;
try {
  schema = JSON.parse(schemaRaw);
} catch (e) {
  fail(`schema is not valid JSON: ${e.message}`);
}
if (schema.$schema !== "https://json-schema.org/draft/2020-12/schema")
  fail(`unexpected $schema: ${schema.$schema}`);
if (schema.$id !== "math-ir://schema/v1.0") fail(`unexpected $id: ${schema.$id}`);
pass(`schema parses (${schemaRaw.length} bytes, $id=${schema.$id})`);

const ajv = new Ajv({ strict: true, allErrors: true });
const validate = ajv.compile(schema);

// structural check (mirror of src/index.ts — gate must not depend on build output)
function checkStructure(root, maxDepth = 64, path = "$.root", seen = new Set(), depth = 0) {
  const issues = [];
  if (depth > maxDepth) return [`${path}: exceeds max depth`];
  if (typeof root !== "object" || root === null) return [`${path}: node must be an object`];
  if (seen.has(root)) return [`${path}: cycle detected`];
  seen.add(root);
  if (root.type === "matrix") {
    const widths = root.rows.map((r) => (Array.isArray(r) ? r.length : -1));
    if (new Set(widths).size > 1) issues.push(`${path}: ragged matrix widths ${widths}`);
    root.rows.forEach((row, i) =>
      (Array.isArray(row) ? row : []).forEach((cell, j) =>
        issues.push(...checkStructure(cell, maxDepth, `${path}.rows[${i}][${j}]`, seen, depth + 1)),
      ),
    );
  }
  seen.delete(root);
  return issues;
}

const files = readdirSync(fixturesDir)
  .filter((f) => f.endsWith(".json") && !f.startsWith("._") && !f.startsWith("."))
  .sort();
const valid = files.filter((f) => !f.startsWith("invalid-"));
const invalid = files.filter((f) => f.startsWith("invalid-"));
if (valid.length < 9) fail(`expected >=9 valid fixtures, found ${valid.length}`);
if (invalid.length < 2) fail(`expected >=2 invalid fixtures, found ${invalid.length}`);

// 2. valid fixtures
for (const f of valid) {
  const doc = JSON.parse(readFileSync(join(fixturesDir, f), "utf8"));
  if (!validate(doc)) fail(`${f} rejected by schema: ${ajv.errorsText(validate.errors)}`);
  const structural = checkStructure(doc.root);
  if (structural.length) fail(`${f} structural issues: ${structural.join("; ")}`);
  pass(`valid fixture ${f}`);
}

// 3a. unknown node must fail JSON Schema
const unknown = JSON.parse(readFileSync(join(fixturesDir, "invalid-unknown-node.json"), "utf8"));
if (validate(unknown)) fail("invalid-unknown-node.json unexpectedly passed schema");
pass("invalid-unknown-node.json correctly rejected by schema");

// 3b. ragged matrix passes schema but must fail structural check
const ragged = JSON.parse(readFileSync(join(fixturesDir, "invalid-ragged-matrix.json"), "utf8"));
const raggedStructural = checkStructure(ragged.root);
if (raggedStructural.length === 0) fail("invalid-ragged-matrix.json passed structural check");
pass(`invalid-ragged-matrix.json correctly flagged (${raggedStructural[0]})`);

// 4. schema hash
const hash = createHash("sha256").update(schemaRaw, "utf8").digest("hex");
console.log(`SCHEMA-GATE OK: schema sha256=${hash}`);
console.log(`SCHEMA-GATE PASS: ${valid.length} valid, ${invalid.length} invalid fixtures`);
