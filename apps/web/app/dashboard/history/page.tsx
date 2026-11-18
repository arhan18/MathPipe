import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import { redirect } from "next/navigation";
import Link from "next/link";
import { DownloadButton } from "./download-button";

export const metadata = { title: "History" };

interface JobRow {
  id: string;
  state: string;
  mode: string;
  warning_count: number;
  error_code: string | null;
  created_at: string;
}

const FRIENDLY: Record<string, string> = {
  uploaded: "Uploaded",
  validating: "Validating",
  queued: "Queued",
  analyzing: "Analyzing",
  processing: "Processing",
  reconstructing: "Reconstructing",
  verifying: "Verifying",
  repairing: "Repairing",
  finalizing: "Finalizing",
  completed: "Ready",
  completed_with_warnings: "Ready with warnings",
  failed: "Failed",
  cancelled: "Cancelled",
  expired: "Expired",
};

export default async function HistoryPage() {
  const jar = await cookies();
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => jar.getAll(), setAll: () => {} } },
  );
  const { data } = await supabase.auth.getUser();
  if (!data.user) redirect("/login?next=/dashboard/history");

  const { data: jobs } = await supabase
    .from("conversion_jobs")
    .select("id,state,mode,warning_count,error_code,created_at")
    .order("created_at", { ascending: false })
    .limit(50);

  const rows = (jobs ?? []) as JobRow[];
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-display text-4xl">History</h1>
      <p className="mt-2 text-neutral-400">
        {rows.length === 0
          ? "No conversions yet."
          : `${rows.length} recent conversion${rows.length === 1 ? "" : "s"}.`}
      </p>
      {rows.length === 0 ? (
        <Link
          href="/convert"
          className="mt-6 inline-block rounded-full bg-white px-6 py-3 text-sm font-semibold text-black"
        >
          Convert your first PDF
        </Link>
      ) : (
        <ul className="mt-8 space-y-3">
          {rows.map((j) => (
            <li
              key={j.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-ink-soft p-4"
            >
              <div>
                <p className="text-sm font-medium">
                  {FRIENDLY[j.state] ?? j.state}
                  <span className="ml-2 text-neutral-500">{j.mode}</span>
                </p>
                <p className="mt-0.5 text-xs text-neutral-500">
                  {new Date(j.created_at).toLocaleString()}
                  {j.state === "completed_with_warnings" ? ` · ${j.warning_count} warnings` : ""}
                  {j.state === "failed" && j.error_code ? ` · ${j.error_code}` : ""}
                </p>
              </div>
              {j.state === "completed" || j.state === "completed_with_warnings" ? (
                <DownloadButton jobId={j.id} />
              ) : j.state === "failed" ? (
                <Link href="/convert" className="text-sm text-neutral-300 underline underline-offset-4">
                  Try again
                </Link>
              ) : (
                <Link
                  href={`/convert?job=${j.id}`}
                  className="text-sm text-neutral-300 underline underline-offset-4"
                >
                  Watch progress
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
