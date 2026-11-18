# Final Audit — scaffold stage (2026-10-06)

Verdict model: **PASS** (verified by execution) · **PARTIAL** (implemented,
not fully proven) · **BLOCKED** (needs live infra) · **DEFERRED** (explicitly
out of MVP scope). Nothing is marked passing on documentation alone.

## 1. Fifteen engineering rules (§80)

| # | Rule | Verdict | Evidence |
|---|---|---|---|
| 1 | No heavy work in request path | PASS | Routes do validation + store ops only; processor is a separate runtime |
| 2 | No service secrets in browser | PASS | Secret sweep clean; service-role only in server files |
| 3 | RLS enforced | PASS | 15/15 tables enabled; service client isolated to webhook/admin |
| 4 | Entitlements server-side only | PASS | Only `transitionForEvent` on verified webhooks changes plans |
| 5 | Webhooks verified + idempotent | PASS | Standard Webhooks verify tested; `event_id` unique ledger |
| 6 | No silent equation→image swaps | PASS | Fallbacks tracked in build report + block metadata |
| 7 | Targeted AI regions only | PASS | Router is region-based; zero AI calls exist yet |
| 8 | Bounded retries | PASS | Repair cap 2, rate buckets, idempotency keys |
| 9 | Single database | PASS | Supabase only; Turso excluded and absent |
| 10 | License gate before weights | PASS | `GatedRecognizer` refuses; quality-gate enforces audit file |
| 11 | Regression before engine swaps | PASS | Golden corpora + benchmark harness + gates runner |
| 12 | Provider boundaries | PASS | AiProvider/JobStore/EmailProvider/ObjectStorage seams |
| 13 | No confidential content in logs | PASS | IDs + timings only; verified by inspection |
| 14 | No absolute quality claims | PASS | Copy audited; thresholds published as targets |
| 15 | Simplest sufficient architecture | PASS | No second DB, no always-on GPU, no RAG |

## 2. Risk acceptance checklist (§64)

| # | Control | Verdict |
|---|---|---|
| 1 | Two evaluated math paths / commercial-safe fallback | PARTIAL — deterministic path live; fallback designed, awaiting licensed weights |
| 2 | Low-confidence equations never silent | PASS |
| 3 | Image fallback tracked | PASS |
| 4 | Matrices / piecewise / aligned / multi-line in corpus | PARTIAL — matrices + cases covered; aligned-equation fixtures missing |
| 5 | MathIR→OMML round-trip suite | PARTIAL — structural suite green; desktop-Word open unverified |
| 6 | Unsupported OMML → explicit fallback | PASS |
| 7 | Per-job AI/GPU budgets server-side | PASS (code; zero live spend) |
| 8 | Bounded verification retries | PASS |
| 9 | License approvals recorded | PASS (re-review at beta) |
| 10 | 500+ page stress without memory growth | PARTIAL — 60 pages / 79 MB proven; 500+ needs GPU workloads |
| 11 | Resume from failed chunk | PASS |
| 12 | Anonymous abuse load-tested | DEFERRED — auth-required launch; controls implemented |
| 13 | CAPTCHA / account escalation | DEFERRED — same reason |
| 14 | Browser close doesn't cancel processing | BLOCKED — needs the worker runtime (Phase 9-ops) |
| 15 | Refresh restores job state | PARTIAL — snapshot + SSE replay live server-side; convert-page client polling not built |
| 16 | SSE/polling reconnect | PARTIAL — server contract implemented; live reconnect untested |
| 17 | Session expiry doesn't kill jobs | PASS (design; activates with worker) |
| 18 | Result access requires authorization | PASS (ownership checks live) |
| 19 | No invented progress percentages | PASS |
| 20 | Two-column benchmark passes | PASS |
| 21 | Expired files actually deleted | PARTIAL — schema + policy live; cleanup cron not built |
| 22 | Webhook duplicates / out-of-order safe | PASS (tested) |
| 23 | Subscription reconciliation | PARTIAL — handler live; reconcile cron not built |
| 24 | Mobile upload/progress/result matrix | PARTIAL — responsive ≥500px verified; sub-500 + device matrix open |

## 3. Production readiness (§78)

**Not production-ready — by design at scaffold stage.** Launch blockers, in order:
1. Live Supabase project + applied migrations + RLS verified with two users
2. Worker runtime (queue → processor → artifact → notify) for durable jobs
3. Dodo + Resend keys, sandbox replay, reconcile + cleanup crons
4. Licensed math/parser weights + real-corpus benchmark win
5. Desktop-Word round-trip + restore drill + device matrix, all recorded

## 4. Cleanliness

- No secrets, no `.env`, no absolute claims, no `console.log` in web code.
- STUB packages remaining (auth, storage, table-engine, figure-engine) are
  tracked future phases, not dead code.
- Content-bearing `.gitkeep` files renamed to `README.md`; `._*` ignored.
- a11y spot-check: 1 h1/page, named controls, lang/title/description present.
- Perf: First Load JS 103–164 kB; WebGL canvases DPR-capped, paused offscreen,
  reduced-motion respected; Lenis skipped under reduced-motion.

## 5. Test inventory (all executed this audit)

Python 53/53 · TS suites green across 25 turbo tasks · quality gates 6/6 PASS ·
live routes 200 with correct 503-gating where live infra is absent.

## 6. End-to-end conversion wiring (2026-10-12 addendum)

First real signup→upload→DOCX→download loop (throwaway user, fully cleaned
up after) found and fixed five defects the scaffold suites could not see:

1. **Missing profiles rows (500 for every new user).** Signups create
   `auth.users` rows but nothing created `profiles`, so `conversion_jobs`
   inserts died on the FK. Fixed with `ensureProfile()` (`@mathpipe/db`,
   called in uploads + feedback) plus canonical trigger migration
   `2026100605_profile_trigger.sql` (pending CLI apply — no CLI creds here).
2. **Illegal initial transition.** Uploads moved `queued → validating`,
   rejected by the machine; the job sat at sequence 0 forever. Creation now
   starts at `uploaded` (`@mathpipe/jobs` + `@mathpipe/db`) and the route
   walks `uploaded → validating → queued`.
3. **Storage key / job-ID split brain.** The route generated a UUID the DB
   ignored (DB minted its own `id`), so stored objects lived under a key no
   consumer could reconstruct. `CreateJobInput` now carries a
   caller-assigned `id` honored by both stores.
4. **pdfjs-dist unusable in this runtime.** The worker file isn't emitted
   into the bundle (and symlinked `.next` breaks node_modules resolution).
   Page counting moved to `pdf-lib` (pure JS, Workers-safe); `pdfjs-dist`
   removed. Verified `pages: 1` on the golden worksheet.
5. **Missing `POST /api/v1/feedback`** (UI already called it) and placeholder
   History page. Both implemented; convert resumes via `?job=`.

Verified live (local build + live Supabase): upload 201 → source round-trip
through Storage → pipeline ok/verify passed → 36,763-byte DOCX → signed-URL
download byte-identical (`PK`) → poll `completed` seq 7 → SSE snapshot +
heartbeat → feedback 201/400 → history renders the job. Gates after the
fixes: web lint + tsc, 18/18 turbo tasks, Python 53/53, quality gates 6/6.
Production worker redeployed (code live on workers.dev; custom-domain route
attach still blocked by token scope). E2E user, jobs, artifacts, usage rows,
feedback, and all 7 storage objects deleted; prefixes verified empty.
