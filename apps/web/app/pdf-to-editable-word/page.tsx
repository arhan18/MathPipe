import type { Metadata } from "next";
import { SeoLanding } from "@/components/seo-landing";
import { canonical } from "@/lib/seo";

export const metadata: Metadata = {
  title: "PDF to Editable Word — Text, Tables and Layout Preserved",
  description:
    "Convert any PDF to truly editable Word: editable text, native tables, preserved layout and reading order — not a flattened export.",
  alternates: { canonical: canonical("/pdf-to-editable-word") },
};

export default function Page() {
  return (
    <SeoLanding
      copy={{
        eyebrow: "PDF → editable Word",
        h1: "A Word file you can actually keep working in",
        lede: "Many converters produce a .docx that is practically frozen: text in boxes, tables as images, pages out of order. MathPipe rebuilds an editable document — paragraphs you can reflow, tables you can extend, headings that navigate.",
        points: [
          {
            title: "Real paragraphs and headings",
            body: "Text becomes flowing paragraphs and true Word headings, so the navigation pane works and styles apply document-wide.",
          },
          {
            title: "Tables you can extend",
            body: "Rows, columns, merged cells and headers arrive as a native table. Add a row for your own data without rebuilding anything.",
          },
          {
            title: "Reading order you can trust",
            body: "Single-column documents read top-to-bottom; multi-column layouts follow column logic. Screen readers and search both benefit.",
          },
        ],
        ctaNote: "Start with the pages you actually need — convert a range, not the whole binder.",
      }}
    />
  );
}
