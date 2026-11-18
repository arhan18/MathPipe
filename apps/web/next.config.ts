import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Phase 1: static-capable shell. Processor/API wiring lands in Phase 2.
  poweredByHeader: false,
  // The Cloudflare adapter consumes the standalone server output. Declaring it
  // here also lets the build run in two steps (see apps/web/scripts/build.sh).
  output: "standalone",
};

export default nextConfig;
