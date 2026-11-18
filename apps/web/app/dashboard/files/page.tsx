import Link from "next/link";
import { Button } from "@/components/ui/button";
import { requireUser } from "@/lib/server-auth";

export const metadata = { title: "Files" };

export default async function FilesPage() {
  await requireUser("/dashboard/files");

  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-display text-4xl">Files</h1>
      <p className="mt-2 text-neutral-400">
        Source PDFs and generated Word documents are available from each conversion.
      </p>

      <div className="mt-8 rounded-2xl border border-white/10 bg-ink-soft p-8 text-center">
        <p className="text-neutral-400">
          File storage is not managed here yet. Download finished documents from your
          conversion history.
        </p>
        <Button variant="outline" className="mt-4" asChild>
          <Link href="/dashboard/history">Open history</Link>
        </Button>
      </div>
    </div>
  );
}
