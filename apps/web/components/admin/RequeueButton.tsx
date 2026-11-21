"use client";

import { Button } from "@/components/ui/button";
import { useState } from "react";
import { requeueJob } from "@/lib/server-actions/requeue-job";

export function RequeueButton({ jobId }: { jobId: string }) {
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const onClick = async () => {
    setBusy(true);
    setMessage(null);
    const form = new FormData();
    form.append("jobId", jobId);
    const res = await requeueJob(form);
    setMessage(res.error ?? (res.ok ? "Requeued." : "Failed."));
    setBusy(false);
  };
  return (
    <span className="inline-flex items-center gap-2">
      <Button type="button" size="sm" variant="outline" disabled={busy} onClick={onClick}>
        {busy ? "Requeueing…" : "Requeue"}
      </Button>
      {message && <span className={message.startsWith("Requeued") ? "text-xs text-emerald-400" : "text-xs text-red-400"}>{message}</span>}
    </span>
  );
}
