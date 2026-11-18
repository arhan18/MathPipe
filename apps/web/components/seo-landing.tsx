import Link from "next/link";
import { ChromeButton } from "@/components/mathpipe/ChromeButton";

export interface SeoLandingCopy {
  eyebrow: string;
  h1: string;
  lede: string;
  points: Array<{ title: string; body: string }>;
  ctaNote: string;
}

/** Shared high-intent landing template. Copy differs per page — never thin duplicates. */
export function SeoLanding({ copy }: { copy: SeoLandingCopy }) {
  return (
    <>
      <section className="mx-auto max-w-3xl px-6 pb-10 pt-16">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">{copy.eyebrow}</p>
        <h1 className="mt-4 font-display text-4xl leading-tight md:text-5xl">{copy.h1}</h1>
        <p className="mt-4 text-lg leading-relaxed text-neutral-400">{copy.lede}</p>
        <div className="mt-8">
          <ChromeButton href="/convert">Convert a PDF free</ChromeButton>
        </div>
      </section>
      <section className="mx-auto max-w-3xl px-6 pb-8">
        <dl className="space-y-6">
          {copy.points.map((p) => (
            <div key={p.title} className="rounded-2xl border border-white/10 bg-ink-soft p-6">
              <dt className="font-display text-xl">{p.title}</dt>
              <dd className="mt-2 text-neutral-400">{p.body}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-8 text-sm text-neutral-500">{copy.ctaNote}</p>
        <div className="mt-4">
          <ChromeButton href="/convert">Open the converter</ChromeButton>
        </div>
      </section>
    </>
  );
}

export function SoftwareAppJsonLd() {
  const json = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "MathPipe",
    applicationCategory: "UtilitiesApplication",
    operatingSystem: "Web",
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
    description:
      "Convert math-heavy PDFs into editable Word documents with native editable equations.",
  };
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(json) }} />;
}
