"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { JobSnapshot } from "@mathpipe/jobs";

/**
 * Live job status: SSE first, polling fallback (§21.1). Truthful stage-only
 * progress — never invented percentages.
 */
export function useJobStatus(jobId: string | null) {
  const [snapshot, setSnapshot] = useState<JobSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);

  const fetchSnapshot = useCallback(async () => {
    if (!jobId) return;
    const res = await fetch(`/api/v1/jobs/${jobId}`, { credentials: "same-origin" });
    if (!res.ok) {
      setError("Could not load job status.");
      return;
    }
    const body = await res.json();
    seq.current = body.job.sequence;
    setSnapshot(body.job);
  }, [jobId]);

  useEffect(() => {
    if (!jobId) return;
    setSnapshot(null);
    setError(null);
    let stopped = false;
    let pollTimer: ReturnType<typeof setInterval> | null = null;

    const startPolling = (everyMs: number) => {
      if (pollTimer) clearInterval(pollTimer);
      const tick = async () => {
        if (stopped) return;
        await fetchSnapshot();
      };
      void tick();
      pollTimer = setInterval(tick, everyMs);
    };

    let source: EventSource | null = null;
    try {
      source = new EventSource(`/api/v1/jobs/${jobId}/events`);
      source.addEventListener("job.snapshot", (e) => {
        const body = JSON.parse((e as MessageEvent).data);
        seq.current = body.job?.sequence ?? body.sequence ?? seq.current;
        if (body.job) setSnapshot(body.job);
      });
      const onStage = (e: Event) => {
        const body = JSON.parse((e as MessageEvent).data);
        if (typeof body.sequence === "number") seq.current = body.sequence;
        void fetchSnapshot();
      };
      for (const t of ["job.stage", "job.warning", "job.completed", "job.failed"]) {
        source.addEventListener(t, onStage);
      }
      source.onerror = () => {
        source?.close();
        source = null;
        if (!stopped) startPolling(4000);
      };
    } catch {
      startPolling(4000);
    }
    void fetchSnapshot();

    return () => {
      stopped = true;
      source?.close();
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [jobId, fetchSnapshot]);

  const terminal = snapshot !== null && ["completed", "completed_with_warnings", "failed", "cancelled", "expired"].includes(snapshot.state);

  return { snapshot, error, terminal };
}
