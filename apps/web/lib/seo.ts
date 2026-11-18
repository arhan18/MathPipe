/** Canonical site URL. Set NEXT_PUBLIC_APP_URL in production. */
export function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_APP_URL ?? "https://mathpipe.app").replace(/\/$/, "");
}

export function canonical(path: string): string {
  return `${siteUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}
