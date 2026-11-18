# MathPipe conversion worker

Drains queued `conversion_jobs` rows: downloads the stored PDF, runs the
Python pipeline, uploads the DOCX, records the artifact, and meters the pages.

Same code runs three ways:

```bash
# from apps/processor, with SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY exported
.venv/bin/python -m worker.service --once          # drain the queue, exit
.venv/bin/python -m worker.service --poll 10       # stay up, poll every 10s
.venv/bin/python -m worker.service --serve 7860    # HTTP mode: POST /run
```

HTTP mode accepts `{"jobId": "<uuid>"}` (also `job_id`), optionally guarded by
`MATHPIPE_WORKER_SECRET` via the `x-worker-secret` header. The web app calls it
through `MODAL_WEBHOOK_URL` after an upload.

Env:

| Variable | Required | Purpose |
| --- | --- | --- |
| `SUPABASE_URL` | yes | Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | Server key (never exposed to the browser) |
| `MATHPIPE_BUCKET` | no | Storage bucket, default `mathpipe-files` |
| `MATHPIPE_CHUNK_PAGES` | no | Pages per pipeline chunk, default `10` |
| `MATHPIPE_WORKER_SECRET` | no | Shared secret for HTTP mode |
| `MATHPIPE_STALL_SECONDS` | no | Re-queue jobs idle this long, default `1800` |

## Deploying on a free host

`Dockerfile` binds `0.0.0.0:7860`, which is what a Hugging Face Docker Space
expects. Build context is `apps/processor`:

```bash
# Hugging Face: new Docker Space -> upload apps/processor, set the two
# Supabase secrets in Settings -> Variables and secrets.
# Then in the Worker:
cd apps/web
pnpm exec wrangler secret put MODAL_WEBHOOK_URL     # https://<space>.hf.space/run
pnpm exec wrangler secret put MATHPIPE_WORKER_SECRET # same value as the Space
```

A Space sleeps when idle; the first upload after a sleep wakes it, and the
request waits for that cold start. `--poll` mode is for an always-on host
(Oracle Always Free ARM, a home server) when cold starts are unacceptable.
