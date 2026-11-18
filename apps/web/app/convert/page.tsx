"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, Suspense } from "react";
import { Button } from "@/components/ui/button";
import { SoftButton } from "@/components/mathpipe/ChromeButton";
import { useJobStatus } from "@/hooks/use-job-status";
import { cn } from "@/lib/utils";

type Mode = "standard" | "verified";
type Phase = "pick" | "uploading" | "working" | "done";

const STAGES = ["uploading", "queued", "analyzing", "processing", "reconstructing", "verifying", "repairing", "finalizing"] as const;

function stageIndex(stage: string): number {
  const i = STAGES.indexOf(stage as (typeof STAGES)[number]);
  return i < 0 ? 0 : i;
}

export default function ConvertPage() {
  return (
    <Suspense>
      <ConvertInner />
    </Suspense>
  );
}

function ConvertInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("standard");
  const [pageRange, setPageRange] = useState("");
  const [phase, setPhase] = useState<Phase>("pick");
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [pages, setPages] = useState<number | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  // Resume watching a job started earlier (linked from History).
  useEffect(() => {
    const resume = searchParams.get("job");
    if (resume && !jobId) {
      setJobId(resume);
      setPhase("working");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);
  const { snapshot, terminal } = useJobStatus(phase === "working" || phase === "done" ? jobId : null);

  const pick = (f: File | undefined) => {
    setError(null);
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setFile(null);
      setError("That file is not a PDF. Choose a file ending in .pdf.");
      return;
    }
    setFile(f);
  };

  const start = () => {
    if (!file) return;
    setError(null);
    setPhase("uploading");
    setUploadPct(0);
    const form = new FormData();
    form.append("file", file);
    form.append("mode", mode);
    if (pageRange.trim()) form.append("pageRange", pageRange.trim());
    form.append("idempotencyKey", crypto.randomUUID());
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/uploads");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setUploadPct(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      setUploadPct(null);
      if (xhr.status === 401) {
        router.push("/login?next=/convert");
        setPhase("pick");
        return;
      }
      let body: { job?: { id: string }; pages?: number | null; error?: { message?: string } } = {};
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        setError("Unexpected server response. Please retry.");
        setPhase("pick");
        return;
      }
      if (xhr.status >= 400 || !body.job) {
        setError(body.error?.message ?? "Upload failed. Please retry.");
        setPhase("pick");
        return;
      }
      setPages(body.pages ?? null);
      setJobId(body.job.id);
      setPhase("working");
      // Keep the job id in the URL so a refresh resumes watching instead of
      // dropping the user back to an empty picker.
      router.replace(`/convert?job=${body.job.id}`);
    };
    xhr.onerror = () => {
      setError("Network error during upload. Please retry.");
      setPhase("pick");
    };
    xhr.send(form);
  };

  const download = async () => {
    if (!jobId || downloading) return;
    setDownloading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/jobs/${jobId}/download`, { credentials: "same-origin" });
      const body = await res.json();
      if (!res.ok || !body.url) {
        setError(body.error?.message ?? "Download is not ready yet.");
        return;
      }
      window.location.href = body.url as string;
    } finally {
      setDownloading(false);
    }
  };

  const state = snapshot?.state;
  const done = phase === "done" || (terminal && (state === "completed" || state === "completed_with_warnings"));
  if (terminal && phase === "working") {
    // Let the result render once the terminal snapshot lands.
    if (state === "completed" || state === "completed_with_warnings") setPhase("done");
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-display text-4xl">Convert a PDF</h1>
      <p className="mt-2 text-neutral-400">
        Best for math, physics, engineering, academic and STEM PDFs. Free plan: 10 pages/month.
      </p>

      {phase === "pick" && (
        <>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              pick(e.dataTransfer.files?.[0]);
            }}
            className="mt-8 block w-full rounded-2xl border border-dashed border-white/20 bg-ink-soft p-12 text-center transition-colors hover:border-white/40"
          >
            <span className="text-lg">{file ? file.name : "Drop your PDF here or choose a file"}</span>
            <span className="mt-1 block text-sm text-neutral-400">
              {file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : "Supported: PDF · plan limits apply"}
            </span>
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            onChange={(e) => pick(e.target.files?.[0])}
          />
          {error && (
            <p role="alert" className="mt-4 rounded-xl border border-red-500/40 bg-red-950/40 p-4 text-sm text-red-200">
              {error}
            </p>
          )}
          {file && !error && (
            <div className="mt-6 rounded-2xl border border-white/10 bg-ink-soft p-6">
              <fieldset>
                <legend className="text-sm font-semibold">Conversion mode</legend>
                <div className="mt-2 flex gap-3">
                  {(["standard", "verified"] as Mode[]).map((m) => (
                    <label
                      key={m}
                      className={cn(
                        "flex-1 cursor-pointer rounded-xl border p-4 text-sm",
                        mode === m ? "border-accent bg-white/5" : "border-white/10",
                      )}
                    >
                      <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => setMode(m)} className="sr-only" />
                      <span className="font-semibold capitalize">{m}</span>
                      <span className="block text-neutral-400">
                        {m === "standard" ? "Fast, low-cost conversion." : "Conversion + AI check and repair. Uses verification allowance."}
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <label className="mt-4 block text-sm">
                <span className="font-semibold">Pages <span className="font-normal text-neutral-400">(optional, e.g. 1–10 or 2, 5, 8–12)</span></span>
                <input
                  value={pageRange}
                  onChange={(e) => setPageRange(e.target.value)}
                  placeholder="Entire document"
                  className="mt-1 w-full rounded-xl border border-white/15 bg-black/30 px-4 py-2.5 outline-none focus:border-accent"
                />
              </label>
              <div className="mt-6">
                <Button size="lg" onClick={start}>Convert</Button>
              </div>
            </div>
          )}
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <SoftButton href="/pricing">Compare plans</SoftButton>
          </div>
        </>
      )}

      {phase === "uploading" && (
        <div className="mt-8 rounded-2xl border border-white/10 bg-ink-soft p-8 text-center" role="status">
          <p className="font-medium">Uploading… {uploadPct ?? 0}%</p>
          <div className="mx-auto mt-4 h-2 max-w-md overflow-hidden rounded-full bg-white/10">
            <div className="h-full bg-accent transition-all" style={{ width: `${uploadPct ?? 0}%` }} />
          </div>
        </div>
      )}

      {(phase === "working" || phase === "done") && (
        <div className="mt-8 rounded-2xl border border-white/10 bg-ink-soft p-8">
          <h2 className="font-semibold">Converting your PDF{pages ? ` · ${pages} pages` : ""}</h2>
          <ol className="mt-4 space-y-2">
            {STAGES.map((s) => {
              const idx = stageIndex(s);
              const cur = snapshot ? stageIndex(snapshot.stage) : 0;
              const finished = snapshot ? idx < cur || terminal : false;
              const current = snapshot?.stage === s && !terminal;
              return (
                <li key={s} className="flex items-center gap-3 text-sm" aria-current={current ? "step" : undefined}>
                  <span aria-hidden="true" className={finished ? "text-green-400" : current ? "text-accent" : "text-neutral-600"}>
                    {finished ? "✓" : current ? "●" : "○"}
                  </span>
                  <span className={finished || current ? "text-neutral-100" : "text-neutral-500"}>
                    {s === "uploading" ? "File uploaded" : s.charAt(0).toUpperCase() + s.slice(1)}
                  </span>
                </li>
              );
            })}
          </ol>

          {snapshot?.state === "queued" && (
            <p className="mt-4 text-xs text-neutral-500" role="status">
              Queued — waiting for the next available processing slot.
            </p>
          )}

          {state === "failed" && (
            <div className="mt-6 rounded-xl border border-red-500/40 bg-red-950/40 p-4 text-sm">
              <p className="text-red-200">We couldn&apos;t complete this conversion.</p>
              <div className="mt-3 flex gap-3">
                <Button size="sm" onClick={() => { setPhase("pick"); setJobId(null); }}>Retry</Button>
                <Button size="sm" variant="outline" onClick={() => { setPhase("pick"); setFile(null); setJobId(null); }}>
                  Upload another PDF
                </Button>
              </div>
            </div>
          )}

          {done && snapshot && (
            <div className="mt-6 border-t border-white/10 pt-6">
              <p className="font-display text-2xl">Your Word document is ready</p>
              {snapshot.warningCount > 0 && (
                <p className="mt-1 text-sm text-accent-warm">
                  Completed with {snapshot.warningCount} region{snapshot.warningCount === 1 ? "" : "s"} to review.
                </p>
              )}
              <div className="mt-4 flex flex-wrap gap-3">
                <Button size="lg" onClick={download} disabled={downloading}>
                  {downloading ? "Preparing…" : "Download DOCX"}
                </Button>
                <Button variant="outline" onClick={() => { setPhase("pick"); setFile(null); setJobId(null); }}>
                  Convert another
                </Button>
              </div>
              <div className="mt-6 flex items-center gap-3 text-sm text-neutral-400">
                <span>How was this conversion?</span>
                <button type="button" aria-label="Great" aria-pressed={feedback === "up"} onClick={() => setFeedback("up")} className={cn("rounded-lg border px-3 py-1", feedback === "up" ? "border-green-400 text-green-300" : "border-white/15")}>👍</button>
                <button type="button" aria-label="Needs improvement" aria-pressed={feedback === "down"} onClick={() => setFeedback("down")} className={cn("rounded-lg border px-3 py-1", feedback === "down" ? "border-red-400 text-red-300" : "border-white/15")}>👎</button>
                {feedback && <span className="text-neutral-500">Thanks — feedback wiring lands with history.</span>}
              </div>
              <p className="mt-4 text-sm">
                <Link href="/dashboard/history" className="text-accent hover:underline">View history</Link>
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
