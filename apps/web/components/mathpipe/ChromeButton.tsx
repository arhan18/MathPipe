import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * ChromeButton — original MathPipe chrome CTA.
 *
 * Polished metal pill: layered silver gradients, top highlight, animated
 * sheen sweep on hover, tactile press state. Pure CSS, built from scratch.
 */
export function ChromeButton({ href, children, className = "" }: { href: string; children: ReactNode; className?: string }) {
  return (
    <Link
      href={href}
      className={cn(
        "group relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-full px-8 py-4",
        "text-base font-semibold text-neutral-900",
        "transition-transform duration-200 hover:scale-[1.02] active:scale-[0.98]",
        className,
      )}
      style={{
        background: "linear-gradient(180deg, #ffffff 0%, #e9edf3 35%, #c6ccd6 62%, #eef1f6 100%)",
        boxShadow:
          "0 10px 30px -8px rgba(180,200,230,0.55), 0 2px 6px rgba(0,0,0,0.5), inset 0 1px 0 #ffffff, inset 0 -1px 0 rgba(90,100,120,0.6)",
        textShadow: "0 1px 0 rgba(255,255,255,0.6)",
      }}
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -translate-x-[150%] skew-x-[-18deg] scale-x-150 bg-gradient-to-r from-transparent via-white/80 to-transparent opacity-0 transition-all duration-700 group-hover:translate-x-[150%] group-hover:opacity-100"
      />
      <span className="relative">{children}</span>
      <svg viewBox="0 0 16 16" className="relative h-4 w-4 transition-transform group-hover:translate-x-1" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M3.2 8h9.1M8.6 4.3 12.4 8l-3.8 3.7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </Link>
  );
}

/**
 * SoftButton — original MathPipe soft-surface CTA.
 *
 * Softly extruded pill on a recessed track with an arrow control.
 * Pure CSS, built from scratch.
 */
export function SoftButton({ href, children, className = "" }: { href: string; children: ReactNode; className?: string }) {
  return (
    <Link
      href={href}
      className={cn(
        "group inline-flex items-center gap-4 rounded-full border border-white/10 bg-[#222a34] py-2 pl-7 pr-2",
        "text-base font-medium text-neutral-200",
        "transition-all duration-300 hover:border-white/25 hover:bg-[#2a3340]",
        className,
      )}
      style={{ boxShadow: "0 14px 34px -12px rgba(0,0,0,0.8), inset 0 1px 0 rgba(255,255,255,0.08)" }}
    >
      <span>{children}</span>
      <span
        aria-hidden="true"
        className="flex h-11 w-11 items-center justify-center rounded-full bg-black/40 transition-transform duration-300 group-hover:translate-x-1"
        style={{ boxShadow: "inset 0 2px 6px rgba(0,0,0,0.7), 0 1px 0 rgba(255,255,255,0.08)" }}
      >
        <svg viewBox="0 0 16 16" className="h-4 w-4 text-neutral-300" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M3.2 8h9.1M8.6 4.3 12.4 8l-3.8 3.7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    </Link>
  );
}
