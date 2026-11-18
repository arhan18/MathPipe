# Implementation Plan — Math PDF → Editable Word

Source of truth: `docs/architecture.md` (v1.3), `docs/prd.md`, `docs/user-flow.md`.
MathIR contract: `packages/document-model/schemas/mathir/v1/math-ir.schema.json`.

Decisions locked before Phase 0: code in `math-pdf-to-word/` subdir, scaffold-only
(no live provider keys), auth-required launch (no anonymous conversion in MVP),
benchmark-only math recognizer (license gate blocks production weights).

## Phases

| # | Name | Builds | Done when |
|---|------|--------|-----------|
| 0 | Foundation & guardrails | Monorepo, CI, MathIR gate, env template | build+lint+typecheck+test 18/18, schema gate passes |
| 1 | Frontend shell | Next.js App Router, design system, marketing, `/convert`, dashboard skeleton | All routes render, responsive, truthful stage progress |
| 2 | Backend API | Job CRUD, SSE+polling (§21.1), signed downloads, rate limits | 12-state machine works against mock processor |
| 3 | Database + quotas | 14 tables, RLS, seed plans, usage ledger | Quota enforced server-side, RLS tests pass |
| 4 | PDF engine | Validation, classification, layout, reading order, DocumentModel | Born-digital PDFs → valid DocumentModel |
| 5 | Math engine (benchmark-only) | MathIR adapter, Marker/Docling + pix2tex Lane A | Corpus → MathIR + confidence, no prod lock-in |
| 6 | DOCX/OMML engine | MathIR→OMML renderer, tables, figures | Word round-trip suite passes |
| 7 | AI verification | Comparison, issue detection, AI router, repair budgets | Seeded errors caught |
| 8 | Long docs + review UI | Chunking, checkpoints, Review Issues page | 500-page stress test resumes from failed chunk |
| 9 | Billing + email + admin | Dodo webhooks, Resend, admin pages | Quota/upgrade flows work with test events |
| 10 | Testing & bugfix | Pyramid targets, gold + red-team corpora, 6 gates | All gates green |
| 11 | SEO + legal + mobile | Landing pages, legal, device matrix | Sitemap + matrix pass |
| 12 | Final audit + beta | License registry, DR drill, 24-item checklist | Launch blockers cleared |

## Rules (§80)

No heavy ML in request path. No service secrets in browser. RLS everywhere.
Entitlements server-side only. Verified + idempotent webhooks. Bounded AI/GPU
retries. License gate before any model weight ships. No engine swap without
regression run. No provider code leaking across boundaries.
