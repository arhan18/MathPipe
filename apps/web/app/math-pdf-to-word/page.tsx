import type { Metadata } from "next";
import { SeoLanding } from "@/components/seo-landing";
import { canonical } from "@/lib/seo";

export const metadata: Metadata = {
  title: "Math PDF to Word Converter — Keep Equations Editable",
  description:
    "Convert math-heavy PDFs into editable Word documents. Fractions, integrals, matrices and symbols stay editable instead of becoming screenshots.",
  alternates: { canonical: canonical("/math-pdf-to-word") },
};

export default function Page() {
  return (
    <SeoLanding
      copy={{
        eyebrow: "Math PDF → Word",
        h1: "The math PDF to Word converter that keeps equations editable",
        lede: "Generic converters flatten mathematics into text or images. MathPipe reconstructs the mathematical structure, so every equation arrives as a native Word equation you can click into and change.",
        points: [
          {
            title: "Built for mathematical notation",
            body: "Fractions, nested fractions, roots, superscripts, subscripts, Greek symbols, matrices and multi-line equations are recognized as mathematics — not as stray characters.",
          },
          {
            title: "Editable beats screenshotted",
            body: "An equation you can edit is worth ten screenshots. Change numbers, swap variables, add steps — the structure survives because it was rebuilt, not photographed.",
          },
          {
            title: "Whole-document fidelity",
            body: "Text, headings, tables, graphs, captions and reading order convert together, so the Word file reads like the PDF instead of a bag of fragments.",
          },
        ],
        ctaNote: "Free plan covers 10 pages a month. No credit card to try.",
      }}
    />
  );
}
