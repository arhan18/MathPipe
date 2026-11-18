import Link from "next/link";
import { Sigma, Table2, Images, Layers, ArrowUpRight, FileCheck2, MousePointer2 } from "lucide-react";
import { ThinkingButtonVisual } from "@/components/threeui/ThinkingButtonVisual";
import { PaperVisual } from "@/components/mathpipe/PaperVisual";
import { GlassSignup } from "@/components/mathpipe/GlassSignup";
import { ChromeButton } from "@/components/mathpipe/ChromeButton";
import { LoupeCompare } from "@/components/mathpipe/LoupeCompare";
import { ChromaHeadline } from "@/components/mathpipe/ChromaHeadline";
import { PricingCards } from "@/components/ui/pricing-cards";
import { TIERS } from "@/lib/plans";
import { SoftwareAppJsonLd } from "@/components/seo-landing";
import { canonical } from "@/lib/seo";

export const metadata = {
  alternates: { canonical: canonical("/") },
};

const FEATURES = [
  {
    n: "01",
    icon: Sigma,
    title: "Native editable equations",
    body: "Fractions, integrals, matrices and multi-line equations arrive as real Word equations you can click into and edit — never screenshots.",
  },
  {
    n: "02",
    icon: Images,
    title: "Graphs and figures stay intact",
    body: "Plots, diagrams and illustrations keep their position, size and appearance next to the text that references them.",
  },
  {
    n: "03",
    icon: Table2,
    title: "Tables stay tables",
    body: "Merged cells, multi-row headers and math inside cells reconstruct as native Word tables.",
  },
  {
    n: "04",
    icon: Layers,
    title: "Structure stays organized",
    body: "Headings, captions, equation numbers, columns and reading order survive the trip — including two-column papers.",
  },
];

const STEPS = [
  { icon: MousePointer2, title: "Drop your PDF", body: "Drag in a math-heavy PDF. We validate pages and size instantly." },
  { icon: FileCheck2, title: "Pick a mode", body: "Standard for speed, Verified for an AI-checked, repaired result." },
  { icon: ArrowUpRight, title: "Download Word", body: "An editable .docx with native equations, tables and figures." },
];

export default function HomePage() {
  return (
    <>
      <SoftwareAppJsonLd />
      {/* Hero — split: copy left, document stage right */}
      <section className="relative mx-auto max-w-7xl px-6 pb-20 pt-14 md:pt-20">
        <div className="grid items-center gap-10 lg:grid-cols-[1.05fr_0.95fr]">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-accent">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
              Math-first PDF → Word
            </p>
            <h1 className="mt-5 font-display text-5xl leading-[1.04] tracking-tight md:text-7xl">
              Turn math PDFs into <em className="text-accent-warm">editable</em> Word documents
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-neutral-400">
              Equations become native Word equations you can click into and change.
              Tables, graphs, captions and two-column layouts survive the trip.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-5">
              <ChromeButton href="/convert">Convert a PDF free</ChromeButton>
              <Link
                href="/how-it-works"
                className="group inline-flex items-center gap-1.5 text-base font-medium text-neutral-300 transition-colors hover:text-white"
              >
                See how it works
                <ArrowUpRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" aria-hidden="true" />
              </Link>
            </div>
            <dl className="mt-10 flex flex-wrap gap-x-10 gap-y-3 border-t border-white/10 pt-6 text-sm">
              <div>
                <dt className="sr-only">Equations per document</dt>
                <dd><span className="font-display text-2xl text-white">147</span> <span className="text-neutral-400">equations / doc avg</span></dd>
              </div>
              <div>
                <dt className="sr-only">Output format</dt>
                <dd><span className="font-display text-2xl text-white">OMML</span> <span className="text-neutral-400">native output</span></dd>
              </div>
              <div>
                <dt className="sr-only">Retention</dt>
                <dd><span className="font-display text-2xl text-white">Auto</span> <span className="text-neutral-400">file deletion</span></dd>
              </div>
            </dl>
          </div>
          <div className="relative">
            <div
              aria-hidden="true"
              className="absolute -inset-6 rounded-[2rem] bg-[radial-gradient(60%_60%_at_50%_40%,rgba(110,168,255,0.12),transparent_70%)]"
            />
            <PaperVisual className="relative h-[420px] w-full md:h-[540px]" />
            <p className="relative mt-2 text-center text-xs text-neutral-500">Live preview — drag the page to tilt it</p>
          </div>
        </div>
      </section>

      {/* Loupe demo */}
      <section aria-label="Conversion demonstration" className="border-t border-white/10 px-6 py-20">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr] lg:items-end">
            <ChromaHeadline>Hover the page.<br />Inspect the Word output.</ChromaHeadline>
            <p className="max-w-md text-neutral-400 lg:justify-self-end">
              The lens magnifies the converted document over the source PDF at 1.9×.
              Every equation under it stays editable.
            </p>
          </div>
          <div className="mt-10">
            <LoupeCompare />
          </div>
          <ul className="mx-auto mt-8 grid max-w-4xl gap-3 text-sm text-neutral-300 sm:grid-cols-3">
            {["Click the equation — it edits", "Graph preserved in place", "Table stays a table"].map((t) => (
              <li key={t} className="rounded-xl border border-white/10 bg-ink-soft px-4 py-3 text-center">
                <span className="mr-2 text-green-400" aria-hidden="true">✓</span>{t}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Upload */}
      <section aria-label="Upload" className="border-t border-white/10 px-6 py-20">
        <div className="mx-auto max-w-7xl">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Start here</p>
            <h2 className="mt-3 font-display text-4xl md:text-5xl">Drop a PDF. Get a document back.</h2>
            <p className="mt-3 text-neutral-400">Best for math, physics, engineering, academic and STEM PDFs. Free plan covers 10 pages a month.</p>
          </div>
          <div className="mt-10 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
            <Link
              href="/convert"
              className="group flex min-h-64 flex-col items-center justify-center gap-4 rounded-3xl border border-dashed border-white/20 bg-ink-soft px-8 py-14 text-center transition-colors hover:border-accent/60 hover:bg-white/[0.03]"
            >
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/5 text-2xl transition-transform group-hover:scale-110" aria-hidden="true">⇪</span>
              <span>
                <span className="block text-lg font-medium">Drop your PDF here or choose a file</span>
                <span className="mt-1 block text-sm text-neutral-400">PDF only · 25 MB max on Free · pages counted before you commit</span>
              </span>
              <span className="text-sm font-semibold text-accent">Open the converter →</span>
            </Link>
            <ol className="flex flex-col justify-center gap-2">
              {STEPS.map((s, i) => (
                <li key={s.title} className="flex gap-4 rounded-2xl border border-white/10 bg-ink-soft p-5">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/5 text-accent">
                    <s.icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <span>
                    <span className="block text-xs font-semibold uppercase tracking-widest text-neutral-500">Step {i + 1}</span>
                    <span className="block font-medium">{s.title}</span>
                    <span className="block text-sm text-neutral-400">{s.body}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
          <div className="mt-8 flex items-center gap-5">
            <div className="h-16 w-64 overflow-hidden rounded-xl" aria-hidden="true">
              <ThinkingButtonVisual />
            </div>
            <p className="max-w-sm text-sm text-neutral-500">Conversion runs asynchronously — close the tab, we email you when it lands.</p>
          </div>
        </div>
      </section>

      {/* Features — editorial numbered rows */}
      <section aria-label="Features" className="border-t border-white/10 px-6 py-20">
        <div className="mx-auto max-w-7xl">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Why it works</p>
          <h2 className="mt-3 max-w-2xl font-display text-4xl md:text-5xl">Built for the documents generic converters destroy</h2>
          <ol className="mt-12">
            {FEATURES.map((f) => (
              <li
                key={f.n}
                className="group grid gap-4 border-t border-white/10 py-8 transition-colors last:border-b hover:bg-white/[0.02] md:grid-cols-[80px_48px_1fr_1.4fr] md:items-center md:gap-8"
              >
                <span className="font-mono text-sm text-neutral-500">{f.n}</span>
                <span className="hidden h-12 w-12 items-center justify-center rounded-2xl bg-white/5 text-accent transition-colors group-hover:bg-accent/15 md:flex">
                  <f.icon className="h-6 w-6" aria-hidden="true" />
                </span>
                <h3 className="font-display text-2xl md:text-3xl">{f.title}</h3>
                <p className="max-w-xl text-neutral-400">{f.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Pricing */}
      <section aria-label="Pricing" className="border-t border-white/10">
        <div className="mx-auto max-w-7xl px-6 pt-20 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Pricing</p>
          <h2 className="mx-auto mt-3 max-w-2xl font-display text-4xl md:text-5xl">Simple, page-based pricing</h2>
          <p className="mx-auto mt-3 max-w-xl text-neutral-400">
            Free tastes the magic. Paid plans scale with your teaching, studying, or publishing.
          </p>
        </div>
        <PricingCards tiers={TIERS} containerClassName="max-w-7xl" className="gap-6 md:grid-cols-2 xl:grid-cols-4" />
      </section>

      {/* Final CTA */}
      <section aria-label="Get started" className="border-t border-white/10 px-6 py-24 text-center">
        <ChromaHeadline className="mx-auto max-w-3xl text-5xl md:text-6xl">Stop retyping math from PDFs.</ChromaHeadline>
        <p className="mx-auto mt-4 max-w-xl text-lg text-neutral-400">
          Upload a PDF and get an editable Word document in minutes. Free to try.
        </p>
        <div className="mt-10 flex justify-center">
          <GlassSignup />
        </div>
      </section>
    </>
  );
}
