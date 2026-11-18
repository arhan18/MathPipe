"use client";

/**
 * ChromaHeadline — original MathPipe chromatic headline.
 *
 * Serif display text that assembles with a red/cyan channel-split sweep when
 * scrolled into view. CSS-only, respects prefers-reduced-motion. Built from
 * scratch; no third-party component source used.
 */

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export function ChromaHeadline({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLHeadingElement>(null);
  const [on, setOn] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setOn(true);
      return undefined;
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setOn(true);
          io.disconnect();
        }
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <h2 ref={ref} className={cn("font-display text-3xl md:text-4xl", className)}>
      <span
        className={cn("inline-block transition-all duration-700", on ? "opacity-100" : "opacity-0")}
        style={
          on
            ? { animation: "mp-chroma-in 0.9s cubic-bezier(0.2,0.75,0.25,1) both" }
            : undefined
        }
      >
        {children}
      </span>
      <style>{`@keyframes mp-chroma-in {
        0% { text-shadow: -6px 0 0 rgba(255,70,90,0.8), 6px 0 0 rgba(80,200,255,0.8); filter: blur(6px); }
        60% { text-shadow: -2px 0 0 rgba(255,70,90,0.4), 2px 0 0 rgba(80,200,255,0.4); filter: blur(0); }
        100% { text-shadow: 0 0 0 transparent; }
      }`}</style>
    </h2>
  );
}
