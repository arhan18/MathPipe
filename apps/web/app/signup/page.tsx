"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { supabaseBrowser } from "@/lib/supabase-client";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    // Confirmation emails return to the PKCE callback, which exchanges the
    // one-time code for a session. Prefer the canonical app URL so links work
    // from the workers.dev host too.
    const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? window.location.origin;
    const { data, error } = await supabaseBrowser().auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${appUrl}/auth/callback` },
    });
    setBusy(false);
    if (error) {
      setError(error.message);
      return;
    }
    if (data.session) {
      router.push("/dashboard");
      router.refresh();
    } else {
      setSent(true);
    }
  };

  return (
    <div className="mx-auto max-w-md px-6 py-16">
      <h1 className="font-display text-4xl">Create account</h1>
      <p className="mt-2 text-neutral-400">Free plan: 10 pages a month. No card required.</p>
      {sent ? (
        <p className="mt-8 rounded-xl border border-white/15 bg-ink-soft p-4 text-sm">
          Check your inbox to confirm your email, then sign in.
        </p>
      ) : (
        <form onSubmit={submit} className="mt-8 space-y-4">
          <label className="block">
            <span className="text-sm text-neutral-400">Email</span>
            <input
              type="email" required autoComplete="email" value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-xl border border-white/15 bg-ink-soft px-4 py-3 outline-none focus:border-accent"
            />
          </label>
          <label className="block">
            <span className="text-sm text-neutral-400">Password (8+ characters)</span>
            <input
              type="password" required minLength={8} autoComplete="new-password" value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-xl border border-white/15 bg-ink-soft px-4 py-3 outline-none focus:border-accent"
            />
          </label>
          {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
          <Button size="lg" className="w-full" disabled={busy}>
            {busy ? "Creating…" : "Create free account"}
          </Button>
        </form>
      )}
      <p className="mt-4 text-sm text-neutral-400">
        Have an account? <Link href="/login" className="text-accent hover:underline">Sign in</Link>
      </p>
    </div>
  );
}
