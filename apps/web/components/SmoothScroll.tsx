"use client";

import { useEffect } from "react";
import Lenis from "lenis";

/** Butter-smooth scrolling. Skipped entirely under prefers-reduced-motion. */
export function SmoothScroll() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;
    const lenis = new Lenis({ autoRaf: true, lerp: 0.1 });
    return () => lenis.destroy();
  }, []);
  return null;
}
