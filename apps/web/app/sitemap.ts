import type { MetadataRoute } from "next";
import { ARTICLES } from "@/lib/content";
import { siteUrl } from "@/lib/seo";

const STATIC = [
  "",
  "/features",
  "/pricing",
  "/how-it-works",
  "/faq",
  "/about",
  "/contact",
  "/convert",
  "/blog",
  "/guides",
  "/compare",
  "/tools",
  "/math-pdf-to-word",
  "/pdf-equations-to-word",
  "/calculus-pdf-to-word",
  "/physics-pdf-to-word",
  "/scientific-pdf-to-word",
  "/editable-equations-word",
  "/pdf-to-editable-word",
  "/privacy",
  "/terms",
  "/cookies",
  "/security",
  "/refund-policy",
  "/data-processing",
];

export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteUrl();
  const now = new Date();
  return [
    ...STATIC.map((p) => ({ url: `${base}${p || "/"}`, lastModified: now })),
    ...ARTICLES.map((a) => ({ url: `${base}/${a.section}/${a.slug}`, lastModified: now })),
  ];
}
