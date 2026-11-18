import { notFound } from "next/navigation";
import { findArticle } from "@/lib/content";
import { canonical } from "@/lib/seo";

export async function generateStaticParams() {
  const { ARTICLES } = await import("@/lib/content");
  return ARTICLES.filter((a) => a.section === "guides").map((a) => ({ slug: a.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = findArticle("guides", slug);
  if (!post) return { title: "Not found" };
  return {
    title: post.title,
    description: post.description,
    alternates: { canonical: canonical(`/guides/${slug}`) },
  };
}

export default async function GuidePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = findArticle("guides", slug);
  if (!post) notFound();
  return (
    <article className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-display text-4xl">{post.title}</h1>
      <p className="mt-3 text-lg text-neutral-400">{post.description}</p>
      {post.body.map((s, i) => (
        <section key={i} className="mt-8">
          {s.heading && <h2 className="font-display text-2xl">{s.heading}</h2>}
          {s.paragraphs.map((p, j) => (
            <p key={j} className="mt-3 leading-relaxed text-neutral-300">{p}</p>
          ))}
        </section>
      ))}
    </article>
  );
}
