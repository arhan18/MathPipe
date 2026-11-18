/**
 * @mathpipe/docx-engine — output artifact validation (§12, §16).
 *
 * The Python processor owns OMML rendering and DOCX packaging; this package
 * is the independent consumer-side verifier: OMML snippet assertions and
 * DOCX container integrity. Renderer and verifier must never share code —
 * otherwise the check proves nothing.
 */

import { readFileSync } from "node:fs";

export const OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math";

/** Required OMML constructs per corpus fixture. */
export const EXPECTED_TAGS: Record<string, string[]> = {
  fraction: ["<m:f>", "<m:num>", "<m:den>"],
  "nested-fraction": ["<m:f>"],
  root: ["<m:rad>"],
  superscript: ["<m:sSup>"],
  fence: ["<m:d>", 'm:val="("'],
  function: ["<m:func>", "<m:fName>"],
  matrix: ["<m:m>", "<m:mr>"],
  limit: ["<m:func>", "<m:fName>"],
  sum: [],
  integral: [],
};

export interface SnippetCheck {
  name: string;
  ok: boolean;
  missing: string[];
}

/** Assert a rendered OMML snippet carries its required constructs. */
export function checkOmmlSnippet(name: string, xml: string): SnippetCheck {
  const required = EXPECTED_TAGS[name] ?? [];
  if (!xml.includes("<m:oMath")) {
    return { name, ok: false, missing: ["<m:oMath"] };
  }
  const missing = required.filter((tag) => !xml.includes(tag));
  return { name, ok: missing.length === 0, missing };
}

/** DOCX container integrity: ZIP magic + plausible size. Deep XML checks
 *  live in the Python suite; this is the cheap gate for web-side artifacts. */
export function checkDocxBytes(data: Uint8Array, minBytes = 10_000): { ok: boolean; reason?: string } {
  if (data.length < 4 || data[0] !== 0x50 || data[1] !== 0x4b || data[2] !== 0x03 || data[3] !== 0x04) {
    return { ok: false, reason: "missing ZIP magic" };
  }
  if (data.length < minBytes) {
    return { ok: false, reason: `suspiciously small (${data.length} bytes)` };
  }
  return { ok: true };
}

export function readFixture(dir: string, name: string): string {
  return readFileSync(`${dir}/${name}`, "utf8");
}
