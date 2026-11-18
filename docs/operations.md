# Operations Runbook (scaffold — live values land with staging)

## Webhook reconciliation (Dodo)

- Reconciliation job compares `billing_events` against Dodo's event list daily.
- Duplicates: safe (unique `event_id`); out-of-order: guarded by active-row check.
- Missing events: backfill by re-fetching from Dodo, then re-run entitlement diff.
- Alert on: webhook failure rate > 1% / 10 min, unprocessed parked events > 0.

## Retention cleanup

- Cron scans `conversion_artifacts` for `expires_at < now() AND deleted_at IS NULL`.
- Delete object from R2 → verify absence → mark `deleted_at` → audit event.
- Retry with backoff; alert after budget exhausted.
- User-requested deletion bypasses the timer (immediate cascade).

## Queue recovery

- DLQ per queue; failed messages move after retry limit, never silently lost.
- Resume rule: reprocess from the failed chunk (`--resume`), never from page 1.
- Alert on: backlog above SLO, p95 wait > 2 min, failure rate > 5% / 10 min.

## Restore drill (blocking for launch)

Demonstrate: database restore, config restore, job-state recovery, billing
reconciliation, interrupted-conversion reprocessing, correct access after
restore. Record date + result in `docs/operations.md` (this file).

| Date | Drill | Result |
|---|---|---|
| — | — | Not yet run (scaffold) |

## Cost guards

- Per-job AI/GPU budgets enforced server-side; router STOPS past budget.
- Alert on: daily AI spend > budget, GPU spike, cost/page p95 breach.
- Margin floors per plan live in architecture §33.1 — recheck after first
  month of measured data.
