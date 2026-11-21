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

function isPdfFile(f: File): boolean {
  return f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");
}

function parseJson(text: string): any {
  try { return JSON.parse(text); } catch { return null; }
}

export default function ConvertPage() {
  return (
    <Suspense>
      <ConvertInner />
    </Suspense>
  );
}

function uploadOnce(
  file: File,
  formBase: FormData,
  onProgress: ((p: number | null) => void) | null,
  onDone: (body: any, status: number) => void,
  onError: (msg: string) => void,
) {
  const form = new FormData();
  formBase.forEach((v, k) => form.append(k, v as string));
  form.append("file", file);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/v1/uploads");
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100));
  };
  xhr.onload = () => onDone(parseJson(xhr.responseText), xhr.status);
  xhr.onerror = () => onError("Network error during upload. Please retry.");
  xhr.send(form);
}

function ConvertInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("standard");
  const [pageRange, setPageRange] = useState("");
  const [phase, setPhase] = useState<Phase>("pick");
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [quotas, setQuotas] = useState<{ planId: string } | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);

  useEffect(() => {
    let active = true;
    fetch("/api/v1/plans/quotas")
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (active) setQuotas(j?.quotas ?? null); })
      .catch(() => { if (active) setQuotas(null); });
    return () => { active = false; };
  }, []);

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

  const batchEnabled = quotas?.planId === "business" && files.length > 1;

  const pick = (list: FileList | undefined) => {
    setError(null);
    const arr = list ? Array.from(list) : [];
    if (arr.length === 0) return;
    const valid = arr.filter(isPdfFile);
    if (valid.length === 0) {
      setFiles([]);
      setError("Choose files ending in .pdf.");
      return;
    }
    setFiles(valid);
  };

  const baseForm = () => {
    const form = new FormData();
    form.append("mode", mode);
    if (pageRange.trim()) form.append("pageRange", pageRange.trim());
    form.append("idempotencyKey", crypto.randomUUID());
    return form;
  };

  const start = () => {
    if (files.length === 0) return;
    setError(null);
    setUploadPct(0);
    setPhase("uploading");
    const done: string[] = [];

    uploadOnce(files[0], baseForm(), setUploadPct, (body, status) => {
      setUploadPct(null);
      if (status === 401) {
        router.push("/login?next=/convert");
        setPhase("pick");
        return;
      }
      if (status >= 400 || !body?.job) {
        setError(body?.error?.message ?? `Upload failed (${status}) for ${files[0].name}. Please retry.`);
        setPhase("pick");
        return;
      }
      done.push(body.job.id);
      if (files.length === 1) {
        setJobId(body.job.id);
        setPhase("working");
        router.replace(`/convert?job=${body.job.id}`);
        return;
      }
      setBatchBusy(true);
      files.slice(1).forEach((f) => {
        uploadOnce(f, baseForm(), null, (b, s) => { if (s < 400 && b?.job) done.push(b.job.id); }, () => undefined);
      });
      setTimeout(() => {
        setBatchBusy(false);
        setFiles([]);
        if (done.length > 0) router.replace(`/convert?job=${done[0]}`);
        else {
          setError("Batch upload finished. Watch each job in History.");
          setPhase("pick");
        }
      }, 30000); // let the last in-flight upload finish
    }, (msg) => {
      setUploadPct(null);
      setError(msg);
      setPhase("pick");
    });
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
              pick(e.dataTransfer.files);
            }}
            className="mt-8 block w-full rounded-2xl border border-dashed border-white/20 bg-ink-soft p-12 text-center transition-colors hover:border-white/40"
          >
            <span className="text-lg">{files.length > 0 ? `${files.length} PDFs ready` : "Drop your PDF here or choose a file"}</span>
            <span className="mt-1 block text-sm text-neutral-400">
              {files.length > 0 ? files.map((f) => f.name).join(", ") : "Supported: PDF · plan limits apply"}
            </span>
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            className="sr-only"
            onChange={(e) => pick(e.target.files?.length ? e.target.files : undefined)}
          />
          {files.length > 1 && (
            <p className="mt-4 text-sm text-neutral-400">
              {batchEnabled
                ? "Each file becomes its own job. Watch all of them in History."
                : `Plan ${quotas?.planId ?? "free"} does not include batch — pass them one at a time.`}
            </p>
          )}
          {error && (
            <p role="alert" className="mt-4 rounded-xl border border-red-500/40 bg-red-950/40 p-4 text-sm text-red-200">
              {error}
            </p>
          )}
          {files.length > 0 && (
            <div className="mt-6 rounded-2xl border border-white/10 bg-ink-soft p-6">
              <fieldset>
                <legend className="text-sm font-semibold">Conversion mode</legend>
                <div className="mt-2 flex gap-3">
                  {(["standard", "verified"] as Mode[]).map((m) => {
                    const disabled = m === "verified";
                    return (
                      <label
                        key={m}
                        className={cn(
                          "flex-1 rounded-xl border p-4 text-sm",
                          disabled ? "cursor-not-allowed border-white/5 opacity-60" : "cursor-pointer",
                          !disabled && (mode === m ? "border-accent bg-white/5" : "border-white/10"),
                        )}
                      >
                        <input
                          type="radio"
                          name="mode"
                          value={m}
                          checked={mode === m}
                          disabled={disabled}
                          onChange={() => setMode(m)}
                          className="sr-only"
                        />
                        <span className="font-semibold capitalize">{m}</span>
                        <span className="block text-neutral-400">
                          {m === "standard" ? "Fast, low-cost conversion." : "Coming soon — AI check and repair is not live yet."}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>
              <label className="mt-4 block text-sm">
                <span className="font-semibold">
                  Pages <span className="font-normal text-neutral-400">(optional, e.g. 1–10 or 2, 5, 8–12)</span>
                </span>
                <input
                  value={pageRange}
                  onChange={(e) => setPageRange(e.target.value)}
                  placeholder="Entire document"
                  className="mt-1 w-full rounded-xl border border-white/15 bg-black/30 px-4 py-2.5 outline-none focus:border-accent"
                />
              </label>
              <div className="mt-6">
                <Button size="lg" onClick={start} disabled={batchBusy}>
                  {batchBusy ? "Batching…" : files.length > 1 ? `Convert ${files.length} PDFs` : "Convert"}
                </Button>
              </div>
            </div>
          )}
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <SoftButton href="/pricing">Compare plans</SoftButton>
          </div>
        </>
      )}

      {phase === "uploading" && (
        <div className="mt-8 p-6">
          <p className="font-medium">Uploading{files.length > 1 ? ` ${files.length} files` : ""}…</p>
          {uploadPct !== null && (
            <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/10">
              <div className="h-full bg-accent" style={{ width: `${uploadPct}%` }} />
            </div>
          )}
        </div>
      )}

      {phase === "working" && (
        <div className="mt-8 p-6">
          <h2 className="font-medium">{done ? "Your document is ready." : "Processing…"}</h2>
          {snapshot && (
            <ol className="mt-4 space-y-2 text-sm text-neutral-300">
              {STAGES.slice(0, stageIndex(snapshot.state)).map((s) => (
                <li key={s}>✓ {s}</li>
              ))}
              {stageIndex(snapshot.state) < STAGES.length && <li className="text-neutral-400">{snapshot.state}…</li>}
              {snapshot.state === "completed" || snapshot.state === "completed_with_warnings" ? (
                <li className="text-neutral-400">Done — see History for all your jobs.</li>
              ) : null}
            </ol>
          )}
          {done && (
            <div className="mt-6">
              <Button onClick={download}>Download .docx</Button>
              <Button variant="outline" className="ml-3" onClick={() => setPhase("pick")}>
                Convert again
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
