import type { Metadata } from "next";
import { SeoLanding } from "@/components/seo-landing";
import { canonical } from "@/lib/seo";

export const metadata: Metadata = {
  title: "Calculus PDF to Word — Integrals, Limits, Derivatives",
  description:
    "Convert calculus PDFs to editable Word: integrals with bounds, limits, derivatives and long derivations stay structured and editable.",
  alternates: { canonical: canonical("/calculus-pdf-to-word") },
};

export default function Page() {
  return (
    <SeoLanding
      copy={{
        eyebrow: "Calculus → Word",
        h1: "Calculus PDFs with integrals and limits intact",
        lede: "Calculus notation is where generic converters fail hardest: bounds detach, long derivations scramble, multi-line steps collapse. MathPipe keeps the structure of each derivation editable.",
        points: [
          {
            title: "Integrals keep their bounds",
            body: "Lower and upper limits stay attached to the integral sign as structured math, so ∫₀¹ f(x) dx remains one editable object.",
          },
          {
            title: "Limits, derivatives, partials",
            body: "Limit expressions, Leibniz and prime notation, and partial derivatives convert as structured notation rather than scattered characters.",
          },
          {
            title: "Multi-step derivations in order",
            body: "Aligned derivation steps keep their sequence and alignment, so a proof still reads as a proof after conversion.",
          },
        ],
        ctaNote: "Built for coursework, lecture notes, and textbook chapters.",
      }}
    />
  );
}
