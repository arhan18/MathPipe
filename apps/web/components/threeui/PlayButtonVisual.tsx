"use client";

import dynamic from "next/dynamic";

const LiquidMetalButton = dynamic(
  () => import("@designcodeio/threeui/components/LiquidMetalButton").then((m) => m.LiquidMetalButton),
  { ssr: false, loading: () => <div className="h-full w-full animate-pulse rounded-full bg-white/5" /> },
);

export function PlayButtonVisual() {
  return <LiquidMetalButton variant="play" rendering="colored" diameter={88} strokeWidth={3.0} text="Play" />;
}
