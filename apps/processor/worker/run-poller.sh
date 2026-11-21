#!/usr/bin/env bash
# Launchd-friendly entrypoint: poll the Supabase job queue every 10s.
# Reads secrets from the local web app env files so nothing is duplicated.
set -euo pipefail

REPO="/Volumes/Arhan/MathPipe/math-pdf-to-word"
WEB="$REPO/apps/web"
PROC="$REPO/apps/processor"

read_var() {
  local file="$1" key="$2"
  [ -f "$file" ] || return 0
  # first match, strip optional quotes
  local line
  line="$(grep -E "^${key}=" "$file" | tail -n 1 || true)"
  [ -n "$line" ] || return 0
  printf '%s' "${line#*=}" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

# Prefer an explicit var, fall back to the public URL (same Supabase project).
: "${SUPABASE_URL:=$(read_var "$WEB/.env" NEXT_PUBLIC_SUPABASE_URL)}"
: "${SUPABASE_SERVICE_ROLE_KEY:=$(read_var "$WEB/.dev.vars" SUPABASE_SERVICE_ROLE_KEY)}"
: "${MATHPIPE_BUCKET:=mathpipe-files}"

export SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY MATHPIPE_BUCKET

if [ -z "${SUPABASE_URL:-}" ] || [ -z "${SUPABASE_SERVICE_ROLE_KEY:-}" ]; then
  echo "mathpipe-worker: missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY" >&2
  exit 1
fi

cd "$PROC"
exec "$PROC/.venv/bin/python" -m worker.service --poll 10
