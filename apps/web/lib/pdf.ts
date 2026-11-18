/** PDF page count without rendering. Pure JS — runs in Node and Workers. */
export async function countPdfPages(bytes: Uint8Array): Promise<number | null> {
  try {
    const { PDFDocument } = await import("pdf-lib");
    const doc = await PDFDocument.load(bytes, { ignoreEncryption: true });
    const pages = doc.getPageCount();
    return Number.isFinite(pages) && pages > 0 ? pages : null;
  } catch (e) {
    console.warn("[pdf] page count failed:", e instanceof Error ? e.message : String(e).slice(0, 200));
    return null;
  }
}

export function looksLikePdf(bytes: Uint8Array): boolean {
  return bytes.length > 4 && bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46;
}
