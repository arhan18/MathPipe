"""MathPipe conversion worker.

Drains `conversion_jobs` rows from `queued` to `completed` by running the
Python pipeline over the stored source PDF, uploading the DOCX, recording the
artifact, and metering the pages consumed.

Two run modes:

  python -m worker.service --once        # drain the current queue, then exit
  python -m worker.service --poll 10     # stay up, poll every 10s
  python -m worker.service --serve 8080  # HTTP POST /run {"jobId": "..."}

Every outward call goes through the Supabase REST API with the service role,
so this stays dependency-free (stdlib only) and portable to any free host.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BUCKET = os.environ.get("MATHPIPE_BUCKET", "mathpipe-files")
DEFAULT_CHUNK_PAGES = int(os.environ.get("MATHPIPE_CHUNK_PAGES", "10"))
STALL_SECONDS = int(os.environ.get("MATHPIPE_STALL_SECONDS", "1800"))
WORKER_SECRET = os.environ.get("MATHPIPE_WORKER_SECRET", "")

# Stage chain the web UI renders. Each step is a legal conversion_jobs state.
STAGE_CHAIN = ["analyzing", "processing", "reconstructing", "finalizing"]


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _ssl_context() -> ssl.SSLContext:
    """python.org builds ship without a CA bundle; fall back to the OS one."""
    ctx = ssl.create_default_context()
    try:
        import certifi  # optional

        ctx.load_verify_locations(certifi.where())
        return ctx
    except Exception:
        pass
    for candidate in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if os.path.exists(candidate):
            ctx.load_verify_locations(candidate)
            break
    return ctx


SSL_CONTEXT = _ssl_context()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Supabase:
    def __init__(self) -> None:
        self.url = _env("SUPABASE_URL").rstrip("/")
        self.key = _env("SUPABASE_SERVICE_ROLE_KEY")
        self.mailer = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}

    def _request(self, method: str, path: str, *, body: bytes | None = None, headers: dict | None = None):
        req = urllib.request.Request(self.url + path, data=body, method=method)
        for k, v in {**self.mailer, **(headers or {})}.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as res:
            raw = res.read()
            return res.status, (json.loads(raw) if raw else None)

    def rest(self, method: str, table: str, query: str = "", payload=None, prefer: str | None = None):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if prefer:
            headers["Prefer"] = prefer
        return self._request(method, f"/rest/v1/{table}{query}", body=body, headers=headers)

    def download(self, key: str) -> bytes:
        req = urllib.request.Request(f"{self.url}/storage/v1/object/{BUCKET}/{key}")
        for k, v in self.mailer.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=300, context=SSL_CONTEXT) as res:
            return res.read()

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        req = urllib.request.Request(f"{self.url}/storage/v1/object/{BUCKET}/{key}", data=data, method="POST")
        for k, v in self.mailer.items():
            req.add_header(k, v)
        req.add_header("Content-Type", content_type)
        req.add_header("x-upsert", "true")
        with urllib.request.urlopen(req, timeout=300, context=SSL_CONTEXT) as res:
            res.read()

    def signed_url(self, key: str, seconds: int = 3600) -> str | None:
        _, data = self._request(
            "POST", f"/storage/v1/object/sign/{BUCKET}/{key}", body=json.dumps({"expiresIn": seconds}).encode(),
            headers={"Content-Type": "application/json"},
        )
        if isinstance(data, dict) and data.get("signedURL"):
            return self.url + "/storage/v1" + data["signedURL"]
        return None


def _plan_limits(db: Supabase, plan_id: str | None) -> tuple[int, int]:
    """(max_pages_per_job, max_file_mb) for the job's plan; free is the floor."""
    if plan_id:
        _, rows = db.rest("GET", "plans", f"?select=max_pages_per_job,max_file_mb&id=eq.{plan_id}")
        if isinstance(rows, list) and rows:
            row = rows[0]
            return int(row.get("max_pages_per_job") or 25), int(row.get("max_file_mb") or 25)
    _, rows = db.rest("GET", "plans", "?select=max_pages_per_job,max_file_mb&id=eq.free")
    if isinstance(rows, list) and rows:
        row = rows[0]
        return int(row.get("max_pages_per_job") or 25), int(row.get("max_file_mb") or 25)
    return 25, 25


def _advance(db: Supabase, job: dict, state: str, **patch) -> bool:
    """Move a job forward. Guarded on the previous sequence so two workers
    can never both own the same job."""
    body = {
        "state": state,
        "sequence": int(job.get("sequence") or 0) + 1,
        "updated_at": _now(),
        **patch,
    }
    status, _ = db.rest(
        "PATCH",
        "conversion_jobs",
        f"?id=eq.{job['id']}&sequence=eq.{int(job.get('sequence') or 0)}",
        body,
        prefer="return=minimal",
    )
    if status >= 400:
        return False
    job["state"] = state
    job["sequence"] = body["sequence"]
    job.update(patch)
    return True


def _record_event(db: Supabase, job: dict, stage: str, message: str, **payload) -> None:
    body = {
        "job_id": job["id"],
        "sequence": int(job.get("sequence") or 0),
        "type": "stage",
        "state": job.get("state", stage),
        "stage": stage,
        "payload": {"message": message, **payload},
    }
    try:
        db.rest("POST", "job_events", "", body, prefer="return=minimal")
    except urllib.error.HTTPError as exc:  # a missing stage row must not kill the job
        print(f"[event] {exc.code} {exc.reason}", flush=True)


def _fail(db: Supabase, job: dict, code: str, message: str, retryable: bool) -> None:
    _advance(db, job, "failed", error_code=code, retryable=retryable)
    _record_event(db, job, "failed", message, errorCode=code, retryable=retryable)
    print(f"[fail] {job['id']} {code}: {message}", flush=True)


def _claim(db: Supabase, job_id: str | None = None) -> dict | None:
    query = "?select=*&state=eq.queued&order=created_at.asc&limit=1"
    if job_id:
        query = f"?select=*&id=eq.{job_id}&limit=1"
    _, rows = db.rest("GET", "conversion_jobs", query)
    if not isinstance(rows, list) or not rows:
        return None
    job = rows[0]
    if job.get("state") not in ("queued", "uploaded", "validating"):
        return None
    # Atomic claim: the filter still pins the old state, so a row another
    # worker already took comes back empty instead of being converted twice.
    sequence = int(job.get("sequence") or 0)
    status, claimed = db.rest(
        "PATCH",
        "conversion_jobs",
        f"?id=eq.{job['id']}&state=in.(queued,uploaded,validating)&sequence=eq.{sequence}",
        {
            "state": "analyzing",
            "sequence": sequence + 1,
            "updated_at": _now(),
            "error_code": None,
        },
        prefer="return=representation",
    )
    if status >= 400 or not isinstance(claimed, list) or not claimed:
        return None
    job["state"] = "analyzing"
    job["sequence"] = sequence + 1
    return job


def run_job(db: Supabase, job: dict) -> bool:
    from src.pipeline.runner import run_pipeline
    from src.word.builder import build_docx

    job_id = job["id"]
    user_id = job["user_id"]
    source_key = job.get("source_artifact_key") or job.get("source_file_id")
    if not source_key:
        _fail(db, job, "INTERNAL", "No stored source for this job.", False)
        return False

    max_pages, max_mb = _plan_limits(db, job.get("plan_id"))
    chunk_pages = min(DEFAULT_CHUNK_PAGES, max(1, max_pages))
    print(f"[run] {job_id} plan={job.get('plan_id') or 'free'} max_pages={max_pages}", flush=True)

    work = tempfile.mkdtemp(prefix=f"mathpipe-{job_id[:8]}-")
    try:
        source = db.download(source_key)
        pdf_path = os.path.join(work, "source.pdf")
        with open(pdf_path, "wb") as fh:
            fh.write(source)

        _record_event(db, job, "analyzing", f"Read {len(source)} bytes from storage.")

        _advance(db, job, "processing")
        _record_event(db, job, "processing", "Reconstructing pages in chunks.")

        result = run_pipeline(
            pdf_path,
            source_name="source.pdf",
            max_bytes=max_mb * 1024 * 1024,
            max_pages=max_pages,
            mode=job.get("mode") or "standard",
            chunk_pages=chunk_pages,
            work_dir=work,
            job_id=job_id,
        )
        if not result.ok or result.model is None:
            _fail(db, job, "CONVERSION_FAILED", result.message or "Pipeline rejected the document.", True)
            return False

        _advance(db, job, "reconstructing")
        data, report = build_docx(result.model, figures=_figures(result.model))
        docx_path = os.path.join(work, "output.docx")
        with open(docx_path, "wb") as fh:
            fh.write(data)

        _advance(db, job, "finalizing")
        output_key = f"users/{user_id}/jobs/{job_id}/output.docx"
        db.upload(
            output_key,
            data,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        db.rest(
            "POST",
            "conversion_artifacts",
            "",
            {
                "job_id": job_id,
                "user_id": user_id,
                "kind": "output",
                "storage_key": output_key,
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size_bytes": len(data),
            },
            prefer="return=minimal",
        )

        pages = int(result.model["document"]["metadata"]["pageCount"])
        fallbacks = int(report.get("equation_fallbacks", 0) or 0)
        missing_figures = int(report.get("figure_missing", 0) or 0)
        warnings = fallbacks + missing_figures
        _advance(
            db,
            job,
            "completed_with_warnings" if warnings else "completed",
            artifact_id=output_key,
            warning_count=warnings,
            error_code=None,
        )
        _record_event(db, job, "completed", "Document ready.", artifactId=output_key, warningCount=warnings)
        _meter(db, job, pages)
        print(
            f"[done] {job_id} {pages}p {len(data)}B equations={report.get('equations')} "
            f"tables={report.get('tables')} figures={report.get('figures')}",
            flush=True,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — one bad job must not stop the queue
        traceback.print_exc()
        _fail(db, job, "INTERNAL", str(exc), True)
        return False
    finally:
        for name in os.listdir(work):
            try:
                os.remove(os.path.join(work, name))
            except OSError:
                pass
        try:
            os.rmdir(work)
        except OSError:
            pass


def _figures(model: dict) -> dict[str, bytes]:
    import base64

    assets: dict[str, bytes] = {}
    for page in model.get("document", {}).get("pages", []) or []:
        for block in (page or {}).get("blocks", []) or []:
            if isinstance(block, dict) and block.get("type") == "figure":
                asset_id, payload = block.get("assetId"), block.get("imageBase64")
                if asset_id and payload:
                    try:
                        assets[str(asset_id)] = base64.b64decode(str(payload))
                    except Exception:
                        continue
    return assets


def _meter(db: Supabase, job: dict, pages: int) -> None:
    """Append the page consumption event the dashboard reads. Idempotent per job."""
    _, existing = db.rest(
        "GET",
        "usage_events",
        f"?select=id&job_id=eq.{job['id']}&kind=eq.conversion_page_consumed&limit=1",
    )
    if isinstance(existing, list) and existing:
        return
    db.rest(
        "POST",
        "usage_events",
        "",
        {
            "user_id": job["user_id"],
            "kind": "conversion_page_consumed",
            "quantity": max(1, pages),
            "job_id": job["id"],
        },
        prefer="return=minimal",
    )


def drain(limit: int = 5) -> int:
    db = Supabase()
    done = 0
    for _ in range(limit):
        job = _claim(db)
        if not job:
            break
        run_job(db, job)
        done += 1
    return done


def _requeue_stalled(db: Supabase) -> None:
    """A crash mid-job leaves a row in a working state forever. Re-queue it."""
    cutoff = datetime.fromtimestamp(time.time() - STALL_SECONDS, timezone.utc).isoformat()
    _, rows = db.rest(
        "GET",
        "conversion_jobs",
        "?select=id,sequence&state=in.(analyzing,processing,reconstructing,finalizing)"
        f"&updated_at=lt.{cutoff}&limit=20",
    )
    for row in rows or []:
        db.rest(
            "PATCH",
            "conversion_jobs",
            f"?id=eq.{row['id']}&sequence=eq.{row['sequence']}",
            {"state": "queued", "sequence": int(row["sequence"]) + 1, "updated_at": _now()},
            prefer="return=minimal",
        )
        print(f"[requeue] {row['id']}", flush=True)


def _run_detached(db: Supabase, job: dict) -> None:
    try:
        run_job(db, job)
    except Exception:  # noqa: BLE001 — a background thread must not kill the server
        traceback.print_exc()


def _http(port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            if self.path.rstrip("/") not in ("/run", "/"):
                self.send_response(404)
                self.end_headers()
                return
            if WORKER_SECRET and self.headers.get("x-worker-secret") != WORKER_SECRET:
                self.send_response(401)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                payload = {}
            db = Supabase()
            try:
                job = _claim(db, payload.get("jobId") or payload.get("job_id"))
            except Exception as exc:  # noqa: BLE001 — report, never drop the socket
                traceback.print_exc()
                body = json.dumps({"ok": False, "error": str(exc)}).encode()
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            # Answer immediately: a 100-page conversion outlives most HTTP
            # proxies (tunnels, free hosts). The client watches the job row.
            body = json.dumps({"ok": True, "accepted": bool(job), "jobId": job["id"] if job else None}).encode()
            self.send_response(202 if job else 409)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            if job:
                Thread(target=_run_detached, args=(db, job), daemon=True).start()

        def do_GET(self):  # noqa: N802
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            return

    print(f"[serve] listening on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


def main() -> int:
    ap = argparse.ArgumentParser(description="MathPipe conversion worker")
    ap.add_argument("--once", action="store_true", help="drain the queue and exit")
    ap.add_argument("--poll", type=int, metavar="SECONDS", help="poll forever")
    ap.add_argument("--serve", type=int, metavar="PORT", help="HTTP worker mode")
    ap.add_argument("--limit", type=int, default=5, help="jobs per drain pass")
    args = ap.parse_args()

    if args.serve:
        _http(args.serve)
        return 0
    if args.once:
        return 0 if drain(args.limit) >= 0 else 1
    if args.poll:
        db = Supabase()
        while True:
            try:
                _requeue_stalled(db)
                drain(args.limit)
            except Exception:  # noqa: BLE001 — the loop must survive transient outages
                traceback.print_exc()
            time.sleep(args.poll)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
