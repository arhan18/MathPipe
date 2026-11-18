import type { Metadata } from "next";
import Link from "next/link";
import "@fontsource/instrument-serif";
import "@fontsource/instrument-serif/400-italic.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/fragment-mono";
import { MathPipeDock } from "@/components/threeui/top-dock/MathPipeDock";
import { SmoothScroll } from "@/components/SmoothScroll";
import { canonical, siteUrl } from "@/lib/seo";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  title: {
    default: "MathPipe — Turn Math PDFs Into Editable Word Documents",
    template: "%s — MathPipe",
  },
  description:
    "Convert equations into native editable Word equations while preserving tables, figures, layout, and document structure.",
  alternates: { canonical: canonical("/") },
  openGraph: {
    type: "website",
    siteName: "MathPipe",
    title: "MathPipe — Turn Math PDFs Into Editable Word Documents",
    description:
      "Convert equations into native editable Word equations while preserving tables, figures, layout, and document structure.",
  },
  twitter: {
    card: "summary_large_image",
    title: "MathPipe — Turn Math PDFs Into Editable Word Documents",
    description:
      "Convert equations into native editable Word equations while preserving tables, figures, layout, and document structure.",
  },
};

function Footer() {
  return (
    <footer className="border-t border-white/10 px-6 py-12">
      <div className="mx-auto grid max-w-6xl gap-8 text-sm text-neutral-400 md:grid-cols-4">
        <div>
          <p className="font-display text-lg text-neutral-100">MathPipe</p>
          <p className="mt-2 max-w-xs">
            The PDF-to-Word converter built specifically for mathematics and STEM.
          </p>
        </div>
        <nav aria-label="Product">
          <p className="font-semibold text-neutral-100">Product</p>
          <ul className="mt-2 space-y-1">
            <li><Link href="/features" className="hover:text-neutral-100">Features</Link></li>
            <li><Link href="/pricing" className="hover:text-neutral-100">Pricing</Link></li>
            <li><Link href="/how-it-works" className="hover:text-neutral-100">How it works</Link></li>
            <li><Link href="/faq" className="hover:text-neutral-100">FAQ</Link></li>
          </ul>
        </nav>
        <nav aria-label="Resources">
          <p className="font-semibold text-neutral-100">Resources</p>
          <ul className="mt-2 space-y-1">
            <li><Link href="/blog" className="hover:text-neutral-100">Blog</Link></li>
            <li><Link href="/guides" className="hover:text-neutral-100">Guides</Link></li>
            <li><Link href="/compare" className="hover:text-neutral-100">Compare</Link></li>
            <li><Link href="/contact" className="hover:text-neutral-100">Contact</Link></li>
          </ul>
        </nav>
        <nav aria-label="Legal">
          <p className="font-semibold text-neutral-100">Trust</p>
          <ul className="mt-2 space-y-1">
            <li><Link href="/privacy" className="hover:text-neutral-100">Privacy</Link></li>
            <li><Link href="/terms" className="hover:text-neutral-100">Terms</Link></li>
            <li><Link href="/security" className="hover:text-neutral-100">Security</Link></li>
            <li><Link href="/refund-policy" className="hover:text-neutral-100">Refunds</Link></li>
          </ul>
        </nav>
      </div>
    </footer>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SmoothScroll />
        <header className="mp-header">
          <MathPipeDock />
        </header>
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
