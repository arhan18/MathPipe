"use client";

import dynamic from "next/dynamic";

const ShaderButtons = dynamic(
  () => import("@designcodeio/threeui/components/ShaderButtons").then((m) => m.ShaderButtons),
  { ssr: false, loading: () => <div className="h-full w-full animate-pulse rounded-xl bg-white/5" /> },
);

export function ThinkingButtonVisual() {
  return <ShaderButtons variant="thinking-button" mode="dark" hue={0} saturation={1.0} brightness={1.0} />;
}
