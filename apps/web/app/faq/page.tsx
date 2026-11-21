export const metadata = { title: "FAQ" };

export default function Page() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-display text-4xl">FAQ</h1>
      <p className="mt-2 text-neutral-400">Answers about formats, limits, verification, privacy, and billing.</p>
      <div className="mt-8 space-y-4">
        <div className="rounded-xl border border-white/10 p-6">
          <h2 className="font-semibold">What format is the output?</h2>
          <p className="mt-2 text-sm text-neutral-400">
            Editable .docx files: real Word equations (OMML), tables, figures, headings and two-column layout. Open in Microsoft Word or Google Docs — no re-export step.
          </p>
        </div>
        <div className="rounded-xl border border-white/10 p-6">
          <h2 className="font-semibold">Is the math editable?</h2>
          <p className="mt-2 text-sm text-neutral-400">Yes. Every equation arrives as a native Word equation, not an image. Click any equation in Word to edit fractions, integrals and matrices.</p>
        </div>
        <div className="rounded-xl border border-white/10 p-6">
          <h2 className="font-semibold">What happens to the original PDF?</h2>
          <p className="mt-2 text-sm text-neutral-400">We keep the source PDF so you can re-download it later from your History. Output files auto-delete after a retention window.</p>
        </div>
        <div className="rounded-xl border border-white/10 p-6">
          <h2 className="font-semibold">What limits apply?</h2>
          <p className="mt-2 text-sm text-neutral-400">Free: 10 pages/month, 25 MB/job. Pro: 500/month, 150/job. Business: 5,000+ pages/month, 250 MB/job.</p>
        </div>
        <div className="rounded-xl border border-white/10 p-6">
          <h2 className="font-semibold">Do you ship AI?</h2>
          <p className="mt-2 text-sm text-neutral-400">Not yet. AI verification modes are marked “coming soon” — everything on the market today is fully usable today.</p>
        </div>
      </div>
    </div>
  );
}
