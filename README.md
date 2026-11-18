# Math PDF → Editable Word

Math-first PDF → editable Word (`.docx`) SaaS. Born-digital math-heavy PDFs in,
native editable Word equations (OMML) out.

> See `docs/architecture.md` (v1.3) for the master blueprint, `docs/prd.md` for
> product requirements, `docs/user-flow.md` for interaction flows.

## Monorepo layout

```text
apps/web          Next.js + React + TypeScript (marketing, tool, dashboard)
apps/processor    Python document-processing runtime (PDF → DocumentModel → DOCX)
packages/*        Shared TypeScript packages (contracts, engines, adapters)
supabase/         Migrations, seed, RLS tests
tests/            unit / integration / e2e / golden-corpus / benchmark
docs/             Canonical product docs (mirrored from ../..)
scripts/          Benchmark, migration, local tooling
configs/models/   Pinned model registry (document / math / verification)
```

## Deploy (Cloudflare Workers via OpenNext)

```bash
# Build outputs go to APFS symlinks (.next, .open-next) — the repo lives on
# exFAT, whose AppleDouble sidecars break bundlers. Never commit those links.
NEXT_PUBLIC_APP_URL=https://mathpipe.arhanahmad.com pnpm --filter @mathpipe/web exec opennextjs-cloudflare build
pnpm --filter @mathpipe/web exec opennextjs-cloudflare deploy
```

Secrets live in Workers (`wrangler secret put`), never in the bundle.
`apps/web/wrangler.jsonc` owns the worker name, routes, and observability.
Live: https://mathpipe-web.aqeelbrh65.workers.dev (custom domain attaches in
dash → Workers → Domains, or via a zone-token with Workers Routes access).

## Quick start (scaffold)

```bash
pnpm install
pnpm test:schema-gate   # MathIR contract gate — must pass before Phase 6
pnpm dev
```

Copy `.env.example` to `apps/web/.env` and fill in provider keys. Never commit `.env`.
(Next.js loads env from `apps/web/` — that file is the live one; `.env.example`
at the root is the template.)

## Engineering rules

Per `docs/architecture.md` §80: no heavy PDF/ML work in the request path, no
service secrets in the browser, RLS enforced, entitlements server-side only,
webhooks verified + idempotent, bounded AI/GPU retries, license gate before
any model weight ships to production.
