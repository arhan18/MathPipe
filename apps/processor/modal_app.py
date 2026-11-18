"""Modal deployment for the MathPipe processor (Phase 9-ops).

Deploy: `modal deploy modal_app.py` (needs MODAL_TOKEN_ID/SECRET).
The webhook is called by the web app after job creation; it runs the staged
pipeline, builds the DOCX, persists artifacts, meters usage, and notifies.

Secrets required in Modal: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
RESEND_API_KEY (optional — notifications skip cleanly without it).
"""
import io
import json
import os
import urllib.request

import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("pypdf==6.19.0", "pdfplumber==0.11.10", "pdfminer.six==20260107",
                 "pillow==12.3.0", "pypdfium2==5.14.0", "python-docx==1.2.0",
                 "jsonschema==4.26.0", "supabase==2.117.2", "resend==2.0.0")
    .add_local_dir("src", remote_path="/root/src")
)

app = modal.App("mathpipe-processor", image=image)

MAX_PAGES = 1000
MAX_SECONDS = 1800


def _supabase():
    from supabase import create_client

    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def _download(supabase, bucket: str, key: str) -> bytes:
    data = supabase.storage.from_(bucket).download(key)
    if isinstance(data, bytes):
        return data
    return data.read() if hasattr(data, "read") else bytes(data)


def _set_state(supabase, job_id: str, state: str, patch: dict | None = None):
    body = {"state": state, "updated_at": "now()"}
    if patch:
        body.update(patch)
    supabase.table("conversion_jobs").update(body).eq("id", job_id).execute()


def _event(supabase, job_id: str, sequence: int, type_: str, state: str, payload: dict | None = None):
    supabase.table("job_events").insert({
        "job_id": job_id, "sequence": sequence, "type": type_,
        "state": state, "stage": state, "payload": payload or {},
    }).execute()


def _notify(email: str | None, subject: str, text: str):
    key = os.environ.get("RESEND_API_KEY", "")
    if not key or not email:
        return
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps({"from": os.environ.get("RESEND_FROM", "MathPipe <hello@arhanahmad.com>"),
                         "to": email, "subject": subject, "text": text}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception:
        pass  # notifications never fail the job


@app.function(timeout=MAX_SECONDS, secrets=[modal.Secret.from_name("mathpipe-prod")])
def run_job(payload: dict):
    """Background worker: full pipeline. Spawned by the webhook, never awaited."""
    import sys

    sys.path.insert(0, "/root")
    from src.cli import _figure_assets_from_model
    from src.pipeline.runner import run_pipeline
    from src.word.builder import build_docx

    supabase = _supabase()
    job_id = payload["job_id"]
    mode = payload.get("mode", "standard")
    page_range = payload.get("page_range")
    if page_range:
        print(f"[modal_app] job {job_id} requested page_range: {page_range}")
    job = supabase.table("conversion_jobs").select("*").eq("id", job_id).maybe_single().execute().data
    if not job:
        return {"ok": False, "error": "unknown job"}

    seq = [int(job.get("sequence", 0))]

    def bump(state: str, patch: dict | None = None):
        seq[0] += 1
        _set_state(supabase, job_id, state, {**(patch or {}), "sequence": seq[0]})
        _event(supabase, job_id, seq[0], "job.stage", state)

    try:
        bump("analyzing")
        pdf_bytes = _download(supabase, payload.get("source_bucket", "mathpipe-files"), payload["source_key"])
        tmp_pdf = f"/tmp/{job_id}.pdf"
        with open(tmp_pdf, "wb") as f:
            f.write(pdf_bytes)

        bump("processing")
        result = run_pipeline(tmp_pdf, source_name="source.pdf",
                              max_bytes=250 * 1024 * 1024, max_pages=MAX_PAGES, mode=mode)
        if not result.ok or result.model is None:
            bump("failed", {"error_code": result.error_code, "retryable": True})
            return {"ok": False, "error": result.error_code}

        bump("reconstructing")
        docx_bytes, report = build_docx(
            result.model, figures=_figure_assets_from_model(result.model))

        out_key = f"users/{job['user_id']}/jobs/{job_id}/output.docx"
        supabase.storage.from_(payload.get("source_bucket", "mathpipe-files")).upload(
            out_key, docx_bytes, {"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "upsert": "true"})
        supabase.table("conversion_artifacts").insert({
            "job_id": job_id, "user_id": job["user_id"], "kind": "output",
            "storage_key": out_key, "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size_bytes": len(docx_bytes),
        }).execute()

        pages = result.model["document"]["metadata"]["pageCount"]
        verified = mode == "verified"
        supabase.table("usage_events").insert({
            "user_id": job["user_id"], "kind": "conversion_page_consumed",
            "quantity": pages, "job_id": job_id}).execute()
        if verified:
            supabase.table("usage_events").insert({
                "user_id": job["user_id"], "kind": "verification_page_consumed",
                "quantity": pages, "job_id": job_id}).execute()

        final = "completed_with_warnings" if not (result.verification or {}).get("shippable", True) else "completed"
        bump("finalizing")
        bump(final, {"artifact_id": out_key,
                     "warning_count": (result.verification or {}).get("issues", 0)})
        _notify(payload.get("user_email"),
                f"Your Word document is ready ({pages} pages)",
                f"Download it from your MathPipe history.")
        return {"ok": True, "pages": pages, "report": report}
    except Exception as exc:  # noqa: BLE001 — job must land failed, never lost
        try:
            bump("failed", {"error_code": "PROCESSING_FAILED", "retryable": True})
        except Exception:
            pass
        return {"ok": False, "error": str(exc)[:200]}


@app.function(secrets=[modal.Secret.from_name("mathpipe-prod")])
@modal.web_endpoint(method="POST")
def convert(payload: dict):
    """Fast-accept endpoint: spawns the worker, returns immediately."""
    run_job.spawn(payload)
    return {"ok": True, "accepted": payload.get("job_id")}
