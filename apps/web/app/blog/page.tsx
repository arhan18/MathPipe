import Link from "next/link";
import { articlesBySection } from "@/lib/content";

export const metadata = { title: "Blog" };

export default function BlogPage() {
  const posts = articlesBySection("blog");
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-display text-4xl">Blog</h1>
      <div className="mt-8 space-y-6">
        {posts.map((p) => (
          <article key={p.slug} className="rounded-2xl border border-white/10 bg-ink-soft p-6">
            <Link href={`/blog/${p.slug}`} className="font-display text-2xl hover:text-accent">{p.title}</Link>
            <p className="mt-2 text-neutral-400">{p.description}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
