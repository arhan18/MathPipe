/**
 * @mathpipe/pdf-engine — DocumentModel v0.1-partial contract (§10).
 *
 * TypeScript mirror of the Python scaffold output. The Python processor is
 * the producer; this package is the consumer-side validator used by the web
 * layer and tests. Math/table/figure stages extend — never reshape — this.
 */

export const DOCUMENT_MODEL_SCHEMA_VERSION = "document-model/v0.1-partial";

export type BlockType = "paragraph" | "heading" | "equation" | "table" | "figure" | "caption" | "list";

export interface BlockStyle {
  fontSize?: number;
  bold?: boolean;
  italic?: boolean;
}

export interface BlockProvenance {
  source: string;
  page: number;
}

export interface DocumentBlock {
  id: string;
  type: string;
  bbox: [number, number, number, number];
  readingOrder: number;
  style: BlockStyle;
  content?: string;
  assetId?: string | null;
  confidence?: number;
  pending?: string;
  provenance?: BlockProvenance;
}

export interface DocumentPage {
  pageNumber: number;
  width: number;
  height: number;
  rotation?: number;
  blocks: DocumentBlock[];
}

export interface DocumentModel {
  schemaVersion: string;
  document: {
    id: string;
    metadata: {
      sourceName: string;
      classification: string;
      pageCount: number;
      producer: string;
    };
    pages: DocumentPage[];
  };
}

export interface ModelIssue {
  path: string;
  message: string;
}

/** Structural validation: shape, page/block consistency, reading order. */
export function validateDocumentModel(model: unknown): ModelIssue[] {
  const issues: ModelIssue[] = [];
  if (typeof model !== "object" || model === null) return [{ path: "$", message: "model must be an object" }];
  const m = model as Partial<DocumentModel>;
  if (m.schemaVersion !== DOCUMENT_MODEL_SCHEMA_VERSION) {
    issues.push({ path: "$.schemaVersion", message: `expected ${DOCUMENT_MODEL_SCHEMA_VERSION}` });
  }
  const doc = m.document;
  if (!doc || typeof doc !== "object") {
    issues.push({ path: "$.document", message: "document is required" });
    return issues;
  }
  if (!Array.isArray(doc.pages)) {
    issues.push({ path: "$.document.pages", message: "pages must be an array" });
    return issues;
  }
  if (doc.metadata?.pageCount !== doc.pages.length) {
    issues.push({ path: "$.document.metadata.pageCount", message: "pageCount disagrees with pages length" });
  }
  doc.pages.forEach((page, pi) => {
    const base = `$.document.pages[${pi}]`;
    if (page.pageNumber !== pi + 1) issues.push({ path: `${base}.pageNumber`, message: "page numbers must be 1-based sequential" });
    if (!Array.isArray(page.blocks)) {
      issues.push({ path: `${base}.blocks`, message: "blocks must be an array" });
      return;
    }
    const orders = page.blocks.map((b) => b.readingOrder);
    const sorted = [...orders].sort((a, b) => a - b);
    if (orders.some((o, i) => o !== sorted[i])) {
      issues.push({ path: `${base}.blocks`, message: "blocks must be stored in reading order" });
    }
    page.blocks.forEach((b, bi) => {
      if (!b.id) issues.push({ path: `${base}.blocks[${bi}].id`, message: "id is required" });
      if (!Array.isArray(b.bbox) || b.bbox.length !== 4 || b.bbox.some((n) => typeof n !== "number" || Number.isNaN(n))) {
        issues.push({ path: `${base}.blocks[${bi}].bbox`, message: "bbox must be 4 finite numbers" });
      }
    });
  });
  return issues;
}

/** Reading-order text extraction: the logical document as the user reads it. */
export function readingOrderText(model: DocumentModel): string[] {
  return model.document.pages.flatMap((p) =>
    p.blocks.filter((b) => typeof b.content === "string").map((b) => b.content as string),
  );
}
