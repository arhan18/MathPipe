import Link from "next/link";
import { Button } from "@/components/ui/button";
import { SignOutButton } from "@/components/sign-out-button";
import { requireUser } from "@/lib/server-auth";

export const metadata = { title: "Settings" };

export default async function SettingsPage() {
  const { user } = await requireUser("/dashboard/settings");

  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-display text-4xl">Settings</h1>

      <div className="mt-8 divide-y divide-white/10 rounded-2xl border border-white/10 bg-ink-soft">
        <div className="flex items-center justify-between gap-4 p-5">
          <span className="text-sm text-neutral-400">Email</span>
          <span className="text-sm">{user.email ?? "—"}</span>
        </div>
        <div className="flex items-center justify-between gap-4 p-5">
          <span className="text-sm text-neutral-400">Session</span>
          <SignOutButton />
        </div>
      </div>

      <p className="mt-6 text-xs text-neutral-500">
        Password and notification preferences follow. See the{" "}
        <Link className="underline" href="/privacy">privacy policy</Link> for data handling.
      </p>
      <div className="mt-4">
        <Button variant="outline" asChild>
          <Link href="/dashboard">Back to dashboard</Link>
        </Button>
      </div>
    </div>
  );
}
