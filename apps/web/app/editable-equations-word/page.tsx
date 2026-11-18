import type { Metadata } from "next";
import { SeoLanding } from "@/components/seo-landing";
import { canonical } from "@/lib/seo";

export const metadata: Metadata = {
  title: "Editable Equations in Word — How They Work",
  description:
    "What makes a Word equation editable, how MathPipe produces native OMML equations from PDFs, and how to edit them yourself.",
  alternates: { canonical: canonical("/editable-equations-word") },
};

export default function Page() {
  return (
    <SeoLanding
      copy={{
        eyebrow: "Editable equations",
        h1: "What 'editable equation' actually means in Word",
        lede: "Click a real Word equation and Word opens its equation tools: you can select the numerator alone, restyle a root, or add a row to a matrix. That is only possible because the file stores structure (OMML), not a picture.",
        points: [
          {
            title: "Structure, not pixels",
            body: "OMML records fractions as numerator-over-denominator, scripts as base-plus-script, matrices as rows of cells. Editing works because the meaning is stored, not just the appearance.",
          },
          {
            title: "How to edit after conversion",
            body: "Click the equation, change any part, press space to let Word re-render. Save normally — the structure survives save and reopen.",
          },
          {
            title: "Why screenshots fail you",
            body: "A pasted equation image cannot be searched, cannot be restyled, blurs when resized, and forces you to rebuild it in the equation editor anyway.",
          },
        ],
        ctaNote: "Convert a page and try editing the equation yourself — that is the whole test.",
      }}
    />
  );
}
