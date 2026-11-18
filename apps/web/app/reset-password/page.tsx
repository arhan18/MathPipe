"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { supabaseBrowser } from "@/lib/supabase-client";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hasSession, setHasSession] = useState<boolean | null>(null);

  useEffect(() => {
    supabaseBrowser()
      .auth.getUser()
      .then(({ data }) => setHasSession(Boolean(data.user)))
      .catch(() => setHasSession(false));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error: updateError } = await supabaseBrowser().auth.updateUser({ password });
    setBusy(false);
    if (updateError) {
      setError(updateError.message);
      return;
    }
    router.push("/dashboard");
    router.refresh();
  };

  if (hasSession === false) {
    return (
      <div className="mx-auto max-w-md px-6 py-16">
        <h1 className="font-display text-4xl">Link expired</h1>
        <p className="mt-2 text-neutral-400">
          Open the newest reset link from your email, or request another one.
        </p>
        <Button className="mt-6" asChild>
          <Link href="/forgot-password">Request a new link</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md px-6 py-16">
      <h1 className="font-display text-4xl">Set a new password</h1>
      <form onSubmit={submit} className="mt-8 space-y-4">
        <label className="block">
          <span className="text-sm text-neutral-400">New password (8+ characters)</span>
          <input
            type="password" required minLength={8} autoComplete="new-password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-xl border border-white/15 bg-ink-soft px-4 py-3 outline-none focus:border-accent"
          />
        </label>
        {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
        <Button size="lg" className="w-full" disabled={busy || hasSession !== true}>
          {busy ? "Saving…" : "Save password"}
        </Button>
      </form>
    </div>
  );
}
