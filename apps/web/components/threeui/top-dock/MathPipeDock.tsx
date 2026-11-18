"use client";

/**
 * Site header dock — modern variant.
 *
 * Motion, spring controller, styling and interaction model vendored verbatim
 * from ThreeUI `AnimatedTopDock` (modern) — MIT © 2026 Meng To
 * (@designcodeio/threeui). Source bundle:
 * https://threeui.com/source-code/animated-top-dock.json
 *
 * Recorded divergences from authored source (content-only, see
 * docs/ui-references.md §1):
 * - MODERN_ITEMS relabelled + given hrefs for the MathPipe IA
 *   (Convert / Features / Pricing / Guides / Dashboard).
 * - Brand word "Lumina" → "MathPipe"; actions link to /login and /convert.
 * - Demo showcase stage + caption removed (this is a site header, not a demo frame).
 * - Buttons → anchor links; active link derived from the current pathname.
 * All spring/shader/controller code paths are byte-identical to the source.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { supabaseBrowser } from "@/lib/supabase-client";
import { createTopDockController, type TopDockOptions } from "./topDockController";
import { cn } from "@/lib/utils";

export type MathPipeDockProps = {
  proximity?: number;
  spring?: number;
  damping?: number;
  widthGrowth?: number;
  heightGrowth?: number;
  drop?: number;
  className?: string;
};

const DEFAULTS = {
  proximity: 122,
  spring: 0.19,
  damping: 0.7,
  widthGrowth: 17,
  heightGrowth: 16,
  drop: 3.5,
} as const;

type DockItem = { id: string; label: string; href: string; icon: ReactNode };

const ITEMS: readonly DockItem[] = [
  { id: "convert", label: "Convert", href: "/convert", icon: <><path d="M8 10.8V2.4M5 5.4 8 2.4l3 3" /><path d="M2.4 10.2v3.4h11.2v-3.4" /></> },
  { id: "features", label: "Features", href: "/features", icon: <><path d="M8 1.9 14.1 5v6L8 14.1 1.9 11V5z" /><path d="M1.9 5 8 8.1 14.1 5M8 8.1v6" /></> },
  { id: "pricing", label: "Pricing", href: "/pricing", icon: <><path d="M8.6 2.2H13v4.4l-6.6 6.6a1.2 1.2 0 0 1-1.7 0L2.2 10.5a1.2 1.2 0 0 1 0-1.7z" /><circle cx="10.6" cy="4.6" r=".9" /></> },
  { id: "guides", label: "Guides", href: "/guides", icon: <><path d="M3.4 2.4h5.4l3.8 3.8v7.4H3.4z" /><path d="M8.8 2.4v3.8h3.8M5.9 9h4.2M5.9 11.2h3" /></> },
  { id: "dashboard", label: "Dashboard", href: "/dashboard", icon: <><rect x="2" y="2" width="12" height="12" rx="2" /><path d="M2 6.4h12M6.4 6.4V14" /></> },
];

const BRAND_MARK = (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <rect width="24" height="24" rx="4.5" fill="#E8E8E3" />
    <path d="M6 6h8.6L18 9.35v8.15H9.15L6 14.35V6Z" fill="#111" />
    <path d="M9 9h5.15L15 9.85V15H9.85L9 14.15V9Z" fill="#E8E8E3" />
    <path d="M12 9v6M9 12h6" stroke="#111" strokeWidth=".7" />
  </svg>
);

function useDockController(getOptions: () => TopDockOptions) {
  const rootRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;
    return createTopDockController(root, getOptions);
    /* the getter is a stable ref reader, so the controller is built once */
  }, []);
  return rootRef;
}

/**
 * Session state for the header actions. `null` while the first read is in
 * flight so the header never flashes "Sign in" at a signed-in user.
 */
function useSessionEmail(): string | null | undefined {
  const [email, setEmail] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    const supabase = supabaseBrowser();
    let active = true;
    supabase.auth
      .getUser()
      .then(({ data }) => {
        if (active) setEmail(data.user?.email ?? null);
      })
      .catch(() => {
        if (active) setEmail(null);
      });
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user?.email ?? null);
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);
  return email;
}

export function MathPipeDock({ className = "", ...props }: MathPipeDockProps) {
  const optionsRef = useRef({ ...DEFAULTS, ...props });
  optionsRef.current = { ...DEFAULTS, ...props };
  const pathname = usePathname();
  const email = useSessionEmail();
  /* lockTrack: the track is pinned to its rest width so the magnified row
     never shoves the brand or the actions around (authored modern behaviour). */
  const rootRef = useDockController(() => ({
    ...optionsRef.current,
    axis: "x" as const,
    distribute: false,
    lockTrack: true,
  }));

  return (
    <div className={cn("animated-top-dock-component atd-modern", className)}>
      <div className="atd-modern__aurora" aria-hidden="true" />
      <header className="atd-modern__bar">
        <Link className="atd-modern__brand" href="/" aria-label="MathPipe home">
          <span className="atd-modern__mark" aria-hidden="true">{BRAND_MARK}</span>
          <span className="atd-modern__word">MathPipe</span>
        </Link>
        <nav ref={rootRef} className="atd-modern__dock" aria-label="Primary" data-dock-state="idle" data-dock-max="0.00">
          {ITEMS.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.id}
                className="atd-modern__item"
                data-dock-item
                href={item.href}
                aria-current={active ? "page" : undefined}
              >
                <span className="atd-modern__icon" aria-hidden="true"><svg viewBox="0 0 16 16">{item.icon}</svg></span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="atd-modern__actions">
          {email === undefined ? (
            <span className="atd-modern__ghost" aria-hidden="true" />
          ) : email ? (
            <Link className="atd-modern__ghost" href="/dashboard" title={email}>
              Dashboard
            </Link>
          ) : (
            <Link className="atd-modern__ghost" href="/login">Sign in</Link>
          )}
          <Link className="atd-modern__cta" href="/convert">
            <span>Convert a PDF</span>
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.2 8h9.1M8.6 4.3 12.4 8l-3.8 3.7" /></svg>
          </Link>
        </div>
      </header>
    </div>
  );
}
