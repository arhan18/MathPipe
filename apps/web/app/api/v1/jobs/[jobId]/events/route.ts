import { toSnapshot, type JobEvent } from "@mathpipe/jobs";
import { API_VERSION, newRequestId } from "@mathpipe/shared";
import { getJobStore, requireUser, checkLimit, apiError } from "@/lib/api";

export const runtime = "nodejs";

/**
 * GET /api/v1/jobs/[jobId]/events — SSE stream (§21.1).
 *
 * Reconnection: client sends Last-Event-ID (sequence); missed events replay
 * from the log when still available, otherwise a fresh snapshot is sent and
 * the client reconciles. Heartbeat every 20s. Client stops on terminal state.
 */

function encode(event: JobEvent | { snapshot: unknown; sequence: number }): string {
  if ("snapshot" in event) {
    return `event: job.snapshot\ndata: ${JSON.stringify({ apiVersion: API_VERSION, ...event })}\n\n`;
  }
  const e = event as JobEvent;
  return `event: ${e.type}\ndata: ${JSON.stringify(e)}\nid: ${e.sequence}\n\n`;
}

export async function GET(req: Request, { params }: { params: Promise<{ jobId: string }> }) {
  const requestId = newRequestId();
  const { jobId } = await params;
  const limited = checkLimit(req, "poll");
  if (!limited.ok) return limited.response;

  const auth = await requireUser();
  if ("response" in auth) return auth.response;

  const store = getJobStore();
  const job = await store.get(jobId);
  if (!job || job.userId !== auth.user.id) {
    return apiError("NOT_FOUND", "No such job.", requestId);
  }

  const lastId = Number(req.headers.get("Last-Event-ID") ?? "NaN");
  const after = Number.isFinite(lastId) ? lastId : job.sequence;
  const missed = await store.eventsSince(jobId, after);

  const stream = new ReadableStream({
    async start(controller) {
      const enc = new TextEncoder();
      const send = (chunk: string) => controller.enqueue(enc.encode(chunk));
      send(encode({ snapshot: toSnapshot(job), sequence: job.sequence }));
      for (const e of missed) send(encode(e));

      let closed = false;
      const heartbeat = setInterval(() => {
        if (closed) return;
        try {
          controller.enqueue(enc.encode(`event: heartbeat\ndata: {"apiVersion":"${API_VERSION}"}\n\n`));
        } catch {
          closed = true;
          clearInterval(heartbeat);
          clearInterval(poller);
        }
      }, 20000);

      let seen = Math.max(job.sequence, ...missed.map((e) => e.sequence), 0);
      const poller = setInterval(async () => {
        if (closed) return;
        try {
          const fresh = await store.eventsSince(jobId, seen);
          for (const e of fresh) {
            send(encode(e));
            seen = Math.max(seen, e.sequence);
          }
        } catch {
          closed = true;
          clearInterval(heartbeat);
          clearInterval(poller);
        }
      }, 2000);

      req.signal.addEventListener("abort", () => {
        closed = true;
        clearInterval(heartbeat);
        clearInterval(poller);
        controller.close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Request-Id": requestId,
    },
  });
}
