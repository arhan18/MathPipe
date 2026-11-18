import type { Metadata } from "next";
import { SeoLanding } from "@/components/seo-landing";
import { canonical } from "@/lib/seo";

export const metadata: Metadata = {
  title: "Scientific PDF to Word — Two-Column Papers, Figures, Tables",
  description:
    "Convert scientific PDFs and two-column academic papers to editable Word with correct reading order, figures, tables and equation numbers.",
  alternates: { canonical: canonical("/scientific-pdf-to-word") },
};

export default function Page() {
  return (
    <SeoLanding
      copy={{
        eyebrow: "Scientific papers → Word",
        h1: "Two-column papers with the reading order intact",
        lede: "Academic PDFs are the hardest layout: two columns, floating figures, tables with math, numbered equations, citations. MathPipe reconstructs the logical reading order — left column, then right — instead of reading across the gutter.",
        points: [
          {
            title: "Column-aware reading order",
            body: "Full-width titles stay on top, then the left column flows top-to-bottom before the right column begins. Figures spanning both columns keep their place.",
          },
          {
            title: "Equation numbers stay linked",
            body: "A numbered equation like (4) keeps its number attached to the equation instead of drifting into the margin as orphan text.",
          },
          {
            title: "Tables with math inside",
            body: "Results tables — including cells containing symbols and expressions — rebuild as native Word tables you can extend with your own rows.",
          },
        ],
        ctaNote: "For researchers converting papers into editable manuscripts and notes.",
      }}
    />
  );
}
