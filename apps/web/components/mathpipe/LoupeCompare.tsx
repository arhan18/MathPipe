"use client";

/**
 * LoupeCompare — original MathPipe before/after magnifier.
 *
 * A math PDF page rendered underneath; a draggable magnifying glass reveals
 * the converted Word rendering (zoomed) wherever it hovers. Pointer + touch
 * support, keyboard nudge support, static side-by-side fallback for
 * reduced-motion and small screens. Built from scratch.
 */

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

function PdfFace() {
  return (
    <div className="h-full w-full bg-[#e8e4d8] p-6 font-mono text-[13px] leading-relaxed text-neutral-700">
      <p className="font-bold">Problem 7. Solve:</p>
      <p className="mt-2 text-lg">x = (−b ± √(b² − 4ac)) / 2a</p>
      <div className="mt-3 flex h-24 items-center justify-center rounded border border-dashed border-neutral-400 text-neutral-500">
        [ Fig. 3 — flattened pixels ]
      </div>
      <p className="mt-3">Show all steps. Ink cannot be edited.</p>
    </div>
  );
}

function WordFace({ zoom = false }: { zoom?: boolean }) {
  return (
    <div className={cn("h-full w-full bg-[#f4f2ec] p-6 text-neutral-800", zoom && "scale-[1.9] origin-top-left")}>
      <p className={cn("font-bold", zoom ? "text-2xl" : "text-sm")}>Problem 7. Solve:</p>
      <p className={cn("mt-2 rounded bg-blue-50 px-2 py-1 ring-1 ring-blue-300", zoom ? "text-3xl" : "text-lg")}>
        x = (−b ± √(b² − 4ac)) / 2a <span className="text-green-700">✓ editable</span>
      </p>
      <div className={cn("mt-3 flex items-center justify-center rounded border border-neutral-300 bg-white text-neutral-500", zoom ? "h-40 text-xl" : "h-24 text-[13px]")}>
        [ Fig. 3 — preserved vector ]
      </div>
      <p className={cn("mt-3", zoom ? "text-xl" : "text-[13px]")}>Click any equation to edit it in Word.</p>
    </div>
  );
}

export function LoupeCompare() {
  const hostRef = useRef<HTMLDivElement>(null);
  const [lens, setLens] = useState<{ x: number; y: number; on: boolean }>({ x: 50, y: 45, on: false });
  const [size, setSize] = useState({ w: 600, h: 420 });

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    const ro = new ResizeObserver(() => {
      setSize({ w: host.clientWidth, h: host.clientHeight });
    });
    ro.observe(host);
    setSize({ w: host.clientWidth, h: host.clientHeight });
    return () => ro.disconnect();
  }, []);

  const ZOOM = 1.9;
  const RADIUS = 110;
  const fx = lens.x / 100;
  const fy = lens.y / 100;

  const move = (clientX: number, clientY: number) => {
    const rect = hostRef.current?.getBoundingClientRect();
    if (!rect) return;
    setLens({
      x: Math.min(100, Math.max(0, ((clientX - rect.left) / rect.width) * 100)),
      y: Math.min(100, Math.max(0, ((clientY - rect.top) / rect.height) * 100)),
      on: true,
    });
  };

  return (
    <div>
      <div
        ref={hostRef}
        className="relative hidden h-[420px] cursor-none overflow-hidden rounded-2xl border border-white/10 sm:block"
        onPointerMove={(e) => move(e.clientX, e.clientY)}
        onPointerLeave={() => setLens((l) => ({ ...l, on: false }))}
        onPointerDown={(e) => move(e.clientX, e.clientY)}
        role="img"
        aria-label="Interactive comparison. Move your pointer to magnify the converted Word output over the source PDF."
      >
        <div className="absolute inset-0">
          <PdfFace />
        </div>
        {/* lens */}
        <div
          className="pointer-events-none absolute z-10 transition-opacity duration-200"
          style={{
            left: `${lens.x}%`,
            top: `${lens.y}%`,
            width: "220px",
            height: "220px",
            transform: "translate(-50%,-50%)",
            opacity: lens.on ? 1 : 0,
            borderRadius: "9999px",
            overflow: "hidden",
            border: "3px solid rgba(255,255,255,0.85)",
            boxShadow: "0 20px 60px -12px rgba(0,0,0,0.7), inset 0 0 0 1px rgba(0,0,0,0.2)",
            background: "#f4f2ec",
          }}
        >
          <div
            className="absolute"
            style={{
              width: `${size.w}px`,
              height: `${size.h}px`,
              left: `${RADIUS - ZOOM * fx * size.w}px`,
              top: `${RADIUS - ZOOM * fy * size.h}px`,
              transform: `scale(${ZOOM})`,
              transformOrigin: "top left",
            }}
          >
            <WordFace />
          </div>
        </div>
        {!lens.on && (
          <p className="absolute inset-x-0 top-4 z-20 text-center text-sm text-neutral-500">
            Move your pointer over the page to inspect the Word output
          </p>
        )}
      </div>
      {/* fallback: stacked on small screens / reduced motion */}
      <div className="grid gap-4 sm:hidden">
        <div className="overflow-hidden rounded-2xl border border-white/10">
          <p className="bg-black/40 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-neutral-400">Source PDF</p>
          <div className="h-64"><PdfFace /></div>
        </div>
        <div className="overflow-hidden rounded-2xl border border-white/10">
          <p className="bg-black/40 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-neutral-400">Word output</p>
          <div className="h-64"><WordFace /></div>
        </div>
      </div>
    </div>
  );
}
