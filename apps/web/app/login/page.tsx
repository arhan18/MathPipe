"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { supabaseBrowser } from "@/lib/supabase-client";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const requested = params.get("next");
  const next = requested && requested.startsWith("/") && !requested.startsWith("//") ? requested : "/dashboard";
  const linkError = params.get("error");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await supabaseBrowser().auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) {
      setError(error.message);
      return;
    }
    router.push(next);
    router.refresh();
  };

  return (
    <div className="mx-auto max-w-md px-6 py-16">
      <h1 className="font-display text-4xl">Sign in</h1>
      {linkError ? (
        <p role="alert" className="mt-4 rounded-xl border border-white/15 bg-ink-soft p-4 text-sm text-neutral-300">
          {linkError}
        </p>
      ) : null}
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
          <span className="text-sm text-neutral-400">Password</span>
          <input
            type="password" required autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-xl border border-white/15 bg-ink-soft px-4 py-3 outline-none focus:border-accent"
          />
        </label>
        {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
        <Button size="lg" className="w-full" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="mt-4 text-sm text-neutral-400">
        No account? <Link href="/signup" className="text-accent hover:underline">Create one</Link>
        {" · "}
        <Link href="/forgot-password" className="text-accent hover:underline">Forgot password</Link>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
