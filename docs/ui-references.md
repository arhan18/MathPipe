# UI References — MathPipe Frontend (Phase 1 input)

Saved integration briefs + source verification log. All briefs say: fetch and
read the complete source before editing; if a source cannot be retrieved, stop
and report instead of recreating.

## 0. Source verification (2026-10-06)

All 8 bundles fetched and confirmed retrievable from threeui.com:

| Component | Bundle URL | Status |
|---|---|---|
| AnimatedTopDock (modern) | https://threeui.com/source-code/animated-top-dock.json | ✅ full component code read |
| MengToSketchbookLandingPage | https://threeui.com/source-code/meng-to-sketchbook-landing-page.json | ✅ dispatcher code read |
| ThreeDPaper (original) | https://threeui.com/source-code/3d-paper.json | ✅ bundle exists |
| ShaderButtons (ignition) | https://threeui.com/source-code/ignition-button.json | ✅ bundle exists |
| ShaderButtons (chrome-upload, soft-surface) | https://threeui.com/source-code/star-portal.json | ✅ dispatcher + variants read |
| GlassAiButton | https://threeui.com/source-code/glass-ai-button.json | ✅ full component code read |
| LiquidMetalButton (play) | https://threeui.com/source-code/liquid-metal-button.json | ✅ full component + canonical source read |
| TextAnimationCollection (threeui-intro) | https://threeui.com/source-code/threeui-intro.json | ✅ bundle exists |
| OrbGallery | https://threeui.com/source-code/orb-gallery.json | ✅ bundle exists |

npm integration path: `@designcodeio/threeui@1.2.0` exists on the public registry.
Package license: **MIT** (code). Binary assets (fonts, images) must still pass
the architecture §9 license gate per-file before production — record each
asset's terms in `docs/license-audit.md` during Phase 1.

Shared stylesheet hash (all bundles): `efe44471…2c8eccf` (`src/shaders/threeui.css`).

## 1. Component → page mapping (MathPipe)

| Surface | Component + variant | Usage |
|---|---|---|
| Site header (all pages) | `AnimatedTopDock` modern | Wordmark left, proximity dock centre, sign-in + gradient CTA right |
| Landing hero concept | `MengToSketchbookLandingPage` mechanics | Page-turn + magnifier mechanics kept; Singapore plates REPLACED with math-PDF plates (textbook page, equation close-up, graph, table) |
| Demo / before-after visual + section bg | `ThreeDPaper` original | Translucent paper as the "editable Word output" visual |
| Upload button (`/convert`) | `ShaderButtons` chrome-upload | Shader chrome upload control |
| Download button (result state) | `ShaderButtons` ignition-button | Tactile ignition control |
| Secondary buttons | `ShaderButtons` soft-surface | Recessed arrow control |
| Signup CTA | `GlassAiButton` | Glass galaxy button |
| Demo video play | `LiquidMetalButton` variant="play" | Circular play control |
| H1 / hero heading | `TextAnimationCollection` threeui-intro | Chromatic wordmark assembly |
| Dashboard analytics | `OrbGallery` + shadcn admin pattern | Reference: https://shadcn-nextjs-admincn-admin-template.vercel.app/dashboard/sales |
| Pricing (`/pricing`) | shadcn `PricingCards` | Code saved in §3 below |
| Math icons | heroicons-animated `CalculatorIcon` | Code saved in §4 below |

### Open Phase 1 items (do NOT silently fork)

1. **Dock labels.** The modern dock's items (Product/Solutions/Docs/Pricing/Changelog)
   are authored inside the component. Our IA needs Convert/Features/Pricing/Docs.
   First check whether installed v1.2.0 exposes items as props; if not, vendor the
   component with a labels-only change and record the divergence.
2. **Sketchbook content.** Mechanics preserved exactly; plate artwork/text becomes
   math-PDF content (our content, their interaction system).
3. **WebGL budget.** Header dock + hero + buttons + gallery = many GL contexts.
   Mount selectively: header always; hero lazily; below-fold canvases behind
   IntersectionObserver (most components already do this); honor
   `prefers-reduced-motion`; pause offscreen. Measure LCP before/after.

## 2. Integration briefs (configured usage)

### 2.1 Header — AnimatedTopDock modern

```tsx
import { AnimatedTopDock } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

export function Scene() {
  return (
    <div className="shader-frame">
      <AnimatedTopDock
        variant="modern"
        proximity={122}
        spring={0.19}
        damping={0.70}
        widthGrowth={17}
        heightGrowth={16}
        drop={3.5}
      />
    </div>
  );
}
```

Source: https://threeui.com/source-code/animated-top-dock.json (rev `5a736cd…`)
Files: `AnimatedTopDock.tsx` (`50ddbba7…`), `topDockController.ts` (`506ab23d…`),
`retroPixelField.ts` (`54f0469b…`), `glassParticleField.ts` (`bc9f07ae…`),
`threeui.css` (`efe44471…`). Asset: `fragment-mono.woff2` (`4f4dc27f…`, 15176 bytes).

### 2.2 Landing concept — MengToSketchbookLandingPage

```tsx
import { MengToSketchbookLandingPage } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

export function Scene() {
  return (
    <div className="shader-frame">
      <MengToSketchbookLandingPage
        headingFont="instrument-serif"
        bodyFont="newsreader"
        headingWeight="400"
        bodyWeight="400"
        primaryColor="#2b2721"
        headingSize={30}
        bodySize={20}
        headingLetterSpacing={0.010}
      />
    </div>
  );
}
```

Source: https://threeui.com/source-code/meng-to-sketchbook-landing-page.json
Canonical HTML: https://threeui.com/landing-pages/meng-to-sketchbook.html
Files: `LandingPages.tsx` (`4d379461…`), `pageTypography.ts` (`809cc657…`),
`pageRecipes.ts` (`c9d9849c…`), `LandingPageFrame.tsx` (`61de2cc5…`),
`meng-to-sketchbook.html` (`e0330548…`). 17 binary assets (9 plates + divider +
wash + bloom + 3 fonts) — copy byte-for-byte, verify hashes from the bundle.

### 2.3 Paper visual / bg — ThreeDPaper original

```tsx
import { ThreeDPaper } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

export function Scene() {
  return (
    <div className="shader-frame">
      <ThreeDPaper variant="original" />
    </div>
  );
}
```

Source: https://threeui.com/source-code/3d-paper.json (rev `8ec1b71c0dbc`)
Files: `3d-paper.html` (`8ec1b71c…`), `ThreeDPaper.tsx` (`c2c8d1e9…`) + 3 variant
sources (site-of-the-year, japanese, certificate).

### 2.4 Buttons — ShaderButtons (ignition / chrome-upload / soft-surface)

```tsx
import { ShaderButtons } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

// Download / primary ignition
<ShaderButtons variant="ignition-button" mode="dark" hue={0} saturation={1.00} brightness={1.00} />
// Upload
<ShaderButtons variant="chrome-upload" mode="dark" hue={0} saturation={1.00} brightness={1.00} />
// Secondary
<ShaderButtons variant="soft-surface" mode="dark" hue={0} saturation={1.00} brightness={1.00} />
```

Sources: https://threeui.com/source-code/ignition-button.json (rev `6f56c4f91814`)
and https://threeui.com/source-code/star-portal.json.
`chrome-upload` = study index 4, `soft-surface` = study index 10 in
`SelectedButtonStudies` (`eca43b8c…`).

### 2.5 Signup — GlassAiButton

```tsx
import { GlassAiButton } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

export function Scene() {
  return (
    <div className="shader-frame">
      <GlassAiButton />
    </div>
  );
}
```

Source: https://threeui.com/source-code/glass-ai-button.json (rev `a484571de316`)
Files: `GlassAiButton.tsx` (`1a11cd58…`), `glass-ai-button.html` (`a484571d…`).

### 2.6 Play — LiquidMetalButton play-circle

```tsx
import { LiquidMetalButton } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

export function Scene() {
  return (
    <div className="shader-frame">
      <LiquidMetalButton variant="play" rendering="colored" diameter={88} strokeWidth={3.0} text="Play" />
    </div>
  );
}
```

Source: https://threeui.com/source-code/liquid-metal-button.json (rev `76624e881a3a`)
Files: `LiquidMetalButton.tsx` (`89b940ba…`), `liquid-metal-button.html` (`76624e88…`).

### 2.7 Headings — TextAnimationCollection threeui-intro

```tsx
import { TextAnimationCollection } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

export function Scene() {
  return (
    <div className="shader-frame">
      <TextAnimationCollection variant="threeui-intro" mode="dark" hue={0} saturation={1.00} brightness={1.00} />
    </div>
  );
}
```

Source: https://threeui.com/source-code/threeui-intro.json
Canonical: `creator-studio-intro.html` (`e14795f2…`).

### 2.8 Analytics — OrbGallery

```tsx
import { OrbGallery } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

export function Scene() {
  return (
    <div className="shader-frame">
      <OrbGallery />
    </div>
  );
}
```

Source: https://threeui.com/source-code/orb-gallery.json (rev `fff1d451248b`)
Dashboard layout reference: https://shadcn-nextjs-admincn-admin-template.vercel.app/dashboard/sales

## 3. Pricing — shadcn PricingCards (pasted source)

Requires: shadcn project, Tailwind, TypeScript, `@radix-ui/react-icons`,
`@radix-ui/react-slot`, `class-variance-authority`. Place at `/components/ui/`.

```tsx
// pricing-cards.tsx
"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CheckIcon, ArrowRightIcon } from "@radix-ui/react-icons";

export interface PricingFeature {
    name: string;
    highlight?: boolean;
    included: boolean;
}

export interface PricingTier {
    name: string;
    price: number;
    interval?: string;
    description: string;
    features: PricingFeature[];
    highlight?: boolean;
    cta?: {
        text: string;
        href?: string;
        onClick?: () => void;
    };
}

export interface PricingCardsProps extends React.HTMLAttributes<HTMLDivElement> {
    tiers: PricingTier[];
    containerClassName?: string;
    cardClassName?: string;
    sectionClassName?: string;
}

export function PricingCards({
    tiers,
    className,
    containerClassName,
    cardClassName,
    sectionClassName,
    ...props
}: PricingCardsProps) {
    return (
        <section
            className={cn(
                "bg-background text-foreground",
                "py-12 sm:py-24 md:py-32 px-4",
                "fade-bottom overflow-hidden pb-0",
                sectionClassName
            )}
        >
            <div className={cn("w-full max-w-5xl mx-auto px-4", containerClassName)} {...props}>
                <div className={cn("grid grid-cols-1 md:grid-cols-2 gap-8", className)}>
                    {tiers.map((tier) => (
                        <div
                            key={tier.name}
                            className={cn(
                                "relative group",
                                "rounded-2xl transition-all duration-500",
                                tier.highlight
                                    ? "bg-gradient-to-b from-neutral-950 to-neutral-900 dark:from-neutral-900 dark:to-neutral-950"
                                    : "bg-white dark:bg-neutral-900",
                                "border border-neutral-200 dark:border-neutral-800",
                                "hover:border-neutral-300 dark:hover:border-neutral-700",
                                "hover:shadow-[0_8px_40px_-12px_rgba(0,0,0,0.1)] dark:hover:shadow-[0_8px_40px_-12px_rgba(0,0,0,0.3)]",
                                cardClassName
                            )}
                        >
                            <div className="p-10 flex flex-col h-full">
                                <div className="space-y-4">
                                    <h3 className={cn(
                                        "text-lg uppercase tracking-wider font-medium",
                                        tier.highlight
                                            ? "text-white"
                                            : "text-neutral-900 dark:text-white"
                                    )}>
                                        {tier.name}
                                    </h3>
                                    <div className="flex items-baseline gap-2">
                                        <span className={cn(
                                            "text-5xl font-light",
                                            tier.highlight
                                                ? "text-white"
                                                : "text-neutral-900 dark:text-white"
                                        )}>
                                            ${tier.price}
                                        </span>
                                        <span className={cn(
                                            "text-sm",
                                            tier.highlight
                                                ? "text-neutral-400"
                                                : "text-neutral-500 dark:text-neutral-400"
                                        )}>
                                            {tier.interval || "one-time"}
                                        </span>
                                    </div>
                                    <p className={cn(
                                        "text-sm pb-6 border-b",
                                        tier.highlight
                                            ? "text-neutral-400 border-neutral-800"
                                            : "text-neutral-500 dark:text-neutral-400 border-neutral-200 dark:border-neutral-800"
                                    )}>
                                        {tier.description}
                                    </p>
                                </div>

                                <div className="mt-8 space-y-4 flex-grow">
                                    {tier.features.map((feature) => (
                                        <div
                                            key={feature.name}
                                            className="flex items-center gap-3"
                                        >
                                            <div className={cn(
                                                "flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center",
                                                feature.included
                                                    ? tier.highlight
                                                        ? "text-white"
                                                        : "text-neutral-900 dark:text-white"
                                                    : "text-neutral-300 dark:text-neutral-700"
                                            )}>
                                                <CheckIcon className="w-3.5 h-3.5" />
                                            </div>
                                            <span className={cn(
                                                "text-sm",
                                                tier.highlight
                                                    ? "text-neutral-300"
                                                    : "text-neutral-600 dark:text-neutral-300"
                                            )}>
                                                {feature.name}
                                            </span>
                                        </div>
                                    ))}
                                </div>

                                {tier.cta && (
                                    <div className="mt-8">
                                        <Button
                                            className={cn(
                                                "w-full h-12 group relative",
                                                tier.highlight
                                                    ? "bg-white hover:bg-neutral-100 text-neutral-900"
                                                    : "bg-neutral-900 hover:bg-neutral-800 text-white dark:bg-white dark:hover:bg-neutral-100 dark:text-neutral-900",
                                                "transition-all duration-300"
                                            )}
                                            onClick={tier.cta.onClick}
                                            asChild={Boolean(tier.cta.href)}
                                        >
                                            {tier.cta.href ? (
                                                <a href={tier.cta.href}>
                                                    <span className="relative z-10 flex items-center justify-center gap-2 font-medium tracking-wide">
                                                        {tier.cta.text}
                                                        <ArrowRightIcon className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                                                    </span>
                                                </a>
                                            ) : (
                                                <span className="relative z-10 flex items-center justify-center gap-2 font-medium tracking-wide">
                                                    {tier.cta.text}
                                                    <ArrowRightIcon className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                                                </span>
                                            )}
                                        </Button>
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}
```

MathPipe tiers (PRD §29 — adapt price/copy at Phase 1, structure as-is):

```tsx
import { PricingCards } from "@/components/blocks/pricing-cards";

const tiers = [
    {
        name: "SELF",
        price: 299,
        description: "For small teams and growing businesses",
        features: [
            { name: "Up to 20 team members", included: true },
            { name: "Advanced analytics", included: true },
            { name: "24/7 email support", included: true },
            { name: "API access", included: true, highlight: true },
            { name: "Custom integrations", included: false },
            { name: "Enterprise features", included: false },
        ],
        cta: { text: "Get started", href: "/signup" }
    },
    {
        name: "TEAM",
        price: 999,
        interval: "monthly",
        description: "For large organizations and enterprises",
        highlight: true,
        features: [
            { name: "Unlimited team members", included: true },
            { name: "Advanced analytics", included: true },
            { name: "24/7 priority support", included: true },
            { name: "Unlimited API access", included: true, highlight: true },
            { name: "Custom integrations", included: true },
            { name: "Enterprise features", included: true },
        ],
        cta: { text: "Contact sales", onClick: () => console.log("Contact sales clicked") }
    },
];

export function PricingPage() {
    return (
        <PricingCards
            tiers={tiers}
            className="gap-6"
            containerClassName="py-12"
        />
    );
}
```

shadcn Button dependency (`@/components/ui/button`):

```tsx
import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  },
)
Button.displayName = "Button"

export { Button, buttonVariants }
```

Install: `@radix-ui/react-icons, @radix-ui/react-slot, class-variance-authority`

## 4. Icons — heroicons-animated CalculatorIcon (pasted source)

Requires: `motion`, `cn` helper at `@/lib/utils` (clsx + tailwind-merge).
Author: Aniket Pawar (@aniket-508), MIT. Source: https://github.com/Aniket-508/heroicons-animated

```tsx
"use client";

import type { Variants } from "motion/react";
import { motion, useAnimation } from "motion/react";
import type { HTMLAttributes } from "react";
import { forwardRef, useCallback, useImperativeHandle, useRef } from "react";
import { cn } from "@/lib/utils";

export interface CalculatorIconHandle {
  startAnimation: () => void;
  stopAnimation: () => void;
}

interface CalculatorIconProps extends HTMLAttributes<HTMLDivElement> {
  size?: number;
}

const BUTTON_VARIANTS: Variants = {
  normal: {
    scale: 1,
    opacity: 1,
  },
  animate: (delay: number) => ({
    scale: [1, 1.5, 1],
    opacity: [1, 0.5, 1],
    transition: {
      duration: 0.15,
      delay: delay * 0.08,
      ease: "easeOut",
    },
  }),
};

const ENTER_VARIANTS: Variants = {
  normal: {
    scale: 1,
    opacity: 1,
  },
  animate: {
    scale: [1, 1.3, 1],
    opacity: [1, 0.6, 1],
    transition: {
      duration: 0.2,
      delay: 0.5,
      ease: "easeOut",
    },
  },
};

const SCREEN_VARIANTS: Variants = {
  normal: {
    opacity: 1,
  },
  animate: {
    opacity: [1, 0.4, 1],
    transition: {
      duration: 0.2,
      delay: 0.65,
      ease: "easeOut",
    },
  },
};

const CalculatorIcon = forwardRef<CalculatorIconHandle, CalculatorIconProps>(
  ({ onMouseEnter, onMouseLeave, className, size = 28, ...props }, ref) => {
    const controls = useAnimation();
    const isControlledRef = useRef(false);

    useImperativeHandle(ref, () => {
      isControlledRef.current = true;

      return {
        startAnimation: () => controls.start("animate"),
        stopAnimation: () => controls.start("normal"),
      };
    });

    const handleMouseEnter = useCallback(
      (e: React.MouseEvent<HTMLDivElement>) => {
        if (isControlledRef.current) {
          onMouseEnter?.(e);
        } else {
          controls.start("animate");
        }
      },
      [controls, onMouseEnter]
    );

    const handleMouseLeave = useCallback(
      (e: React.MouseEvent<HTMLDivElement>) => {
        if (isControlledRef.current) {
          onMouseLeave?.(e);
        } else {
          controls.start("normal");
        }
      },
      [controls, onMouseLeave]
    );

    return (
      <div
        className={cn(className)}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        {...props}
      >
        <svg
          fill="none"
          height={size}
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
          viewBox="0 0 24 24"
          width={size}
          xmlns="http://www.w3.org/2000/svg"
        >
          <path d="M12 2.25C10.108 2.25 8.24156 2.35947 6.40668 2.57241C5.30608 2.70014 4.5 3.649 4.5 4.75699V19.5C4.5 20.7426 5.50736 21.75 6.75 21.75H17.25C18.4926 21.75 19.5 20.7426 19.5 19.5V4.75699C19.5 3.649 18.6939 2.70014 17.5933 2.57241C15.7584 2.35947 13.892 2.25 12 2.25Z" />
          <motion.path
            animate={controls}
            d="M8.25 6H15.75V8.25H8.25V6Z"
            initial="normal"
            variants={SCREEN_VARIANTS}
          />
          <motion.path
            animate={controls}
            custom={0}
            d="M8.25 11.25H8.2575V11.2575H8.25V11.25Z"
            initial="normal"
            variants={BUTTON_VARIANTS}
          />
          <motion.path
            animate={controls}
            custom={2}
            d="M10.7476 11.25H10.7551V11.2575H10.7476V11.25Z"
            initial="normal"
            variants={BUTTON_VARIANTS}
          />
          <motion.path
            animate={controls}
            custom={1}
            d="M13.2524 13.5H13.2599V13.5075H13.2524V13.5Z"
            initial="normal"
            variants={BUTTON_VARIANTS}
          />
          <motion.path
            animate={controls}
            custom={4}
            d="M8.25 15.75H8.2575V15.7575H8.25V15.75Z"
            initial="normal"
            variants={BUTTON_VARIANTS}
          />
          <motion.path
            animate={controls}
            custom={3}
            d="M15.75 11.25H15.7575V11.2575H15.75V11.25Z"
            initial="normal"
            variants={BUTTON_VARIANTS}
          />
          <motion.path
            animate={controls}
            custom={5}
            d="M10.7476 18H10.7551V18.0075H10.7476V18Z"
            initial="normal"
            variants={BUTTON_VARIANTS}
          />
          <path d="M8.25 13.5H8.2575V13.5075H8.25V13.5Z" />
          <path d="M8.25 18H8.2575V18.0075H8.25V18Z" />
          <path d="M10.7476 13.5H10.7551V13.5075H10.7476V13.5Z" />
          <path d="M10.7476 15.75H10.7551V15.7575H10.7476V15.75Z" />
          <path d="M13.2524 11.25H13.2599V11.2575H13.2524V11.25Z" />
          <path d="M13.2524 15.75H13.2599V15.7575H13.2524V15.75Z" />
          <path d="M13.2524 18H13.2599V18.0075H13.2524V18Z" />
          <path d="M15.75 13.5H15.7575V13.5075H15.75V13.5Z" />
          <motion.path
            animate={controls}
            d="M15.75 15.75V18"
            initial="normal"
            variants={ENTER_VARIANTS}
          />
        </svg>
      </div>
    );
  }
);

CalculatorIcon.displayName = "CalculatorIcon";

export { CalculatorIcon };
```

## 6. Pro verdict + original builds (2026-10-06)

**Do NOT copy Pro sources.** Verified: `ThreeDPaper`, `GlassAiButton`,
`OrbGallery`, `chrome-upload` / `soft-surface` studies and related Pro
variants are absent from the MIT Community package (v1.2.0) and from the
public Community repo (404 on `main`) — they are Pro catalog items
(`GET PRO` on their pages). Copying their source would violate their terms
and architecture §9/§80-rule-10. Reference screenshots taken for design
study only (`/tmp/pro-paper.png`, `/tmp/pro-buttons.png`).

Instead, original MathPipe equivalents were built from scratch in
`apps/web/components/mathpipe/` (no third-party component source used):

| Ask | Original build | Placement |
|---|---|---|
| 3D paper bg | `PaperVisual` — Three.js translucent math document, ∫ watermark, drag + inertia | Home hero backdrop |
| Glass signup | `GlassSignup` — glass pill, canvas galaxy orb, particle burst → /signup | Home final CTA |
| Chrome upload | `ChromeButton` — CSS chrome pill, sheen sweep | Upload section CTA |
| Soft secondary | `SoftButton` — extruded pill, recessed arrow | Convert page → pricing |
| Chromatic heading | `ChromaHeadline` — channel-split assemble on scroll | Demo + CTA headlines |
| Orb analytics | `OrbStats` — CSS-3D stat sphere, drag + hover | Dashboard snapshot |
| Sketchbook loupe | `LoupeCompare` — draggable magnifier over source PDF revealing zoomed Word output | Home demo (replaces static grid) |

Deferred: full sketchbook-with-math-plates (needs 9 artworks — content task).

## 5. Phase 1 package-truth findings (installed v1.2.0)

The briefs describe the latest catalog; the shippable Community package differs.
Rules derived from verification (do not regress):

1. **Deep imports only.** Never import the package barrel (`@designcodeio/threeui`
   root) — it pulls incompatible modules and breaks the Next build. Use
   `@designcodeio/threeui/components/<Name>` + `@designcodeio/threeui/style.css`.
2. **Client-only mounting.** WebGL/iframe showcases must load via
   `next/dynamic` with `ssr: false` (+ skeleton fallback) — they crash
   prerender otherwise. Wrappers live in `apps/web/components/threeui/`.
3. **NOT in v1.2.0 (Pro-only): `ThreeDPaper`, `GlassAiButton`, `OrbGallery`,
   `chrome-upload` / `soft-surface` studies.** Package-exact substitutes used:
   - Upload visual → `ShaderButtons variant="thinking-button"` (the brief documents
     legacy `uploading-button` → `thinking-button`; same intent).
   - Secondary CTA visual → shadcn Button (functional link; shader studies are
     fixed-size stages, not inline buttons).
   - Signup CTA → shadcn Button (`GlassAiButton` bakes "GPT 6 Sol" branding).
   - Paper/output visual → `EngravedCertificate` (package-exact certificate scene).
   - Dashboard → clean usage cards (orb deferred with the backend).
   - H1 → custom serif headline (`threeui-intro` bakes the "ThreeUI" wordmark).
4. **Vendored (one): `MathPipeDock`.** `AnimatedTopDock` exposes no `items` prop
   and its buttons don't navigate — unusable as a real header package-exact.
   Vendored under MIT (© 2026 Meng To, attribution in file): controller
   byte-identical; modern markup kept; only brand word, 5 IA labels + hrefs,
   link actions, and demo stage/caption changed. Divergence recorded here.
5. **Deferred:** sketchbook-with-math-plates (needs 9 replacement artworks —
   content task, tracked for Phase 1b); `OrbGallery` analytics visual.
6. **License gate:** package code MIT, ThreeUI-authored assets MIT, bundled
   fonts OFL 1.1, Three.js MIT — recorded from the package's LICENSE,
   ASSET-LICENSES.md, FONT-LICENSES.md. No Pro/Beta sources included.
7. **Harness note:** headless Chrome clamps layout viewport to ≥500px, so
   sub-500px layouts cannot be screenshot-verified here — verified instead by
   in-browser width audit (body == viewport, zero offenders at 500px) plus
   wrapping grids, `text-3xl` hero, and `overflow-x: hidden`.

