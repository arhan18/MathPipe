import type { Metadata } from "next";
import { SeoLanding } from "@/components/seo-landing";
import { canonical } from "@/lib/seo";

export const metadata: Metadata = {
  title: "Physics PDF to Word — Formulas, Units, Diagrams",
  description:
    "Convert physics PDFs to editable Word: formulas with units, vectors, multi-line derivations and diagrams preserved in place.",
  alternates: { canonical: canonical("/physics-pdf-to-word") },
};

export default function Page() {
  return (
    <SeoLanding
      copy={{
        eyebrow: "Physics → Word",
        h1: "Physics PDFs: formulas, units and diagrams together",
        lede: "Physics documents mix prose, mathematics, units and figures on every page. MathPipe converts all four together, keeping each figure next to the derivation that references it.",
        points: [
          {
            title: "Vectors, units and subscripts",
            body: "Vector notation, unit expressions (m/s², kg·m) and indexed variables survive as structured content instead of collapsing into plain text.",
          },
          {
            title: "Diagrams stay with derivations",
            body: "Free-body diagrams, circuit sketches and plots keep their position, size and captions — the figure your text says 'see Fig. 3' is still Fig. 3.",
          },
          {
            title: "Problem sets become editable",
            body: "Turn a PDF problem set into a Word worksheet: change numbers, reorder questions, add parts — without retyping a single formula.",
          },
        ],
        ctaNote: "Ideal for JEE/NEET/GATE prep material and lab reports.",
      }}
    />
  );
}
