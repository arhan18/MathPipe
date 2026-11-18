"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

/** Fetches the signed download URL, then navigates — keeps the URL out of markup. */
export function DownloadButton({ jobId }: { jobId: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <Button
        size="sm"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            const res = await fetch(`/api/v1/jobs/${jobId}/download`);
            if (!res.ok) throw new Error(`Download failed (${res.status}).`);
            const body = (await res.json()) as { url?: string };
            if (!body.url) throw new Error("No download URL returned.");
            window.location.href = body.url;
          } catch (e) {
            setError(e instanceof Error ? e.message : "Download failed.");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Preparing…" : "Download .docx"}
      </Button>
      {error ? <span className="text-xs text-red-400">{error}</span> : null}
    </span>
  );
}
