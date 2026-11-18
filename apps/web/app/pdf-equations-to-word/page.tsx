import type { Metadata } from "next";
import { SeoLanding } from "@/components/seo-landing";
import { canonical } from "@/lib/seo";

export const metadata: Metadata = {
  title: "PDF Equations to Editable Word Equations (OMML)",
  description:
    "Turn PDF equations into native editable Word equations. Click any formula in Word and edit it — fractions, integrals, matrices included.",
  alternates: { canonical: canonical("/pdf-equations-to-word") },
};

export default function Page() {
  return (
    <SeoLanding
      copy={{
        eyebrow: "Equations → Word",
        h1: "PDF equations become Word equations you can actually edit",
        lede: "Word's native equation format (OMML) keeps mathematical structure editable. MathPipe converts recognized equations into OMML — open the file, click a formula, change it, save.",
        points: [
          {
            title: "How native equations work",
            body: "A Word equation stores numerators, denominators, bases and scripts as structure. That is why you can select just the exponent, or replace a denominator, without rebuilding anything.",
          },
          {
            title: "What stays editable",
            body: "Fractions, roots, integrals with bounds, summations, matrices, piecewise definitions and aligned multi-line derivations — each as structured OMML, not pixels.",
          },
          {
            title: "Honest about limits",
            body: "If a construct cannot be represented safely, it is preserved visibly and flagged — never silently morphed into a different equation.",
          },
        ],
        ctaNote: "Try it on one page free and click the equation yourself.",
      }}
    />
  );
}
