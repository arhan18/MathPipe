#!/usr/bin/env bash
# Cloudflare build for MathPipe.
#
# The repo lives on an exFAT volume. macOS cannot store extended attributes
# there, so every file written by the toolchain leaves an AppleDouble
# companion (`._name`). Next's own bundler then tries to parse `._page` as a
# page and fails. Strip those companions between the two build phases.
set -euo pipefail

cd "$(dirname "$0")/.."

strip_appledouble() {
  find "$1" -name '._*' -delete 2>/dev/null || true
}

rm -rf .next .open-next

NEXT_PUBLIC_APP_URL="${NEXT_PUBLIC_APP_URL:-https://mathpipe.arhanahmad.com}" \
NEXT_TELEMETRY_DISABLED=1 \
  pnpm exec next build
strip_appledouble .next

NEXT_PUBLIC_APP_URL="${NEXT_PUBLIC_APP_URL:-https://mathpipe.arhanahmad.com}" \
NEXT_TELEMETRY_DISABLED=1 \
  pnpm exec opennextjs-cloudflare build --skipNextBuild --dangerouslyUseUnsupportedNextVersion

strip_appledouble .open-next
echo "build: ok"
