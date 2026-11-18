"use client";

/**
 * GlassSignup — original MathPipe glass CTA.
 *
 * A frosted-glass pill with a canvas starfield orb, spark icon and a
 * particle burst on activation. Links to /signup. Built from scratch;
 * no third-party component source used.
 */

import Link from "next/link";
import { useEffect, useRef } from "react";

function drawOrb(canvas: HTMLCanvasElement) {
  const ctx = canvas.getContext("2d")!;
  const dpr = Math.min(window.devicePixelRatio, 2);
  const size = 56 * dpr;
  canvas.width = size;
  canvas.height = size;
  // deep-blue galaxy disc
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "#9db8ff");
  g.addColorStop(0.35, "#4a6fd4");
  g.addColorStop(0.7, "#1b2452");
  g.addColorStop(1, "rgba(10,12,30,0)");
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2, 0, Math.PI * 2);
  ctx.fill();
  // stars (seeded)
  let seed = 42;
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };
  ctx.fillStyle = "#fff";
  for (let i = 0; i < 40; i++) {
    const a = rand() * Math.PI * 2;
    const r = rand() * size * 0.42;
    const s = rand() * 1.6 * dpr + 0.4;
    ctx.globalAlpha = 0.4 + rand() * 0.6;
    ctx.beginPath();
    ctx.arc(size / 2 + Math.cos(a) * r, size / 2 + Math.sin(a) * r, s, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

type Particle = { x: number; y: number; vx: number; vy: number; life: number };

export function GlassSignup({ href = "/signup", label = "Create free account" }: { href?: string; label?: string }) {
  const orbRef = useRef<HTMLCanvasElement>(null);
  const burstRef = useRef<HTMLCanvasElement>(null);
  const particles = useRef<Particle[]>([]);
  const raf = useRef(0);

  useEffect(() => {
    if (orbRef.current) drawOrb(orbRef.current);
  }, []);

  const burst = (e: React.MouseEvent) => {
    const canvas = burstRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio, 2);
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    const ctx = canvas.getContext("2d")!;
    const cx = (e.clientX - rect.left) * dpr;
    const cy = (e.clientY - rect.top) * dpr;
    for (let i = 0; i < 46; i++) {
      const a = Math.random() * Math.PI * 2;
      const sp = (2 + Math.random() * 5) * dpr;
      particles.current.push({ x: cx, y: cy, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp, life: 1 });
    }
    cancelAnimationFrame(raf.current);
    const tick = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.current = particles.current.filter((p) => p.life > 0);
      for (const p of particles.current) {
        p.x += p.vx;
        p.y += p.vy;
        p.vx *= 0.96;
        p.vy *= 0.96;
        p.life -= 0.03;
        ctx.globalAlpha = Math.max(0, p.life);
        ctx.fillStyle = "#bcd0ff";
        ctx.beginPath();
        ctx.arc(p.x, p.y, 2 * dpr * p.life + 0.5, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      if (particles.current.length) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
  };

  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  return (
    <Link
      href={href}
      onClick={burst}
      className="group relative inline-flex items-center gap-3 overflow-hidden rounded-full border border-white/25 bg-white/10 py-1.5 pl-1.5 pr-6 backdrop-blur-xl transition-transform duration-300 hover:scale-[1.03] active:scale-[0.98]"
      style={{ boxShadow: "0 8px 40px -8px rgba(110,168,255,0.45), inset 0 1px 0 rgba(255,255,255,0.25)" }}
    >
      <span className="relative h-12 w-12 overflow-hidden rounded-full">
        <canvas ref={orbRef} className="h-full w-full" aria-hidden="true" />
        <svg viewBox="0 0 24 24" className="absolute inset-0 m-auto h-6 w-6 text-white/90" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" strokeLinecap="round" />
          <circle cx="12" cy="12" r="3.2" />
        </svg>
      </span>
      <span className="text-base font-semibold tracking-wide text-white">{label}</span>
      <svg viewBox="0 0 16 16" className="h-4 w-4 text-white/70 transition-transform group-hover:translate-x-1" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
        <path d="M3.2 8h9.1M8.6 4.3 12.4 8l-3.8 3.7" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <canvas ref={burstRef} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true" />
    </Link>
  );
}
