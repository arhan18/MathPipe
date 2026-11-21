import { headers } from "next/headers";

/**
 * Country of the current request, from the CDN edge header Cloudflare sets.
 * Returns an empty string when the header is absent (local dev, non-edge
 * clients), which callers treat as "use default pricing".
 */
export async function resolveCountry(): Promise<string> {
  const store = await headers();
  const raw = store.get("cf-ipcountry") ?? store.get("x-vercel-ip-country") ?? "";
  const code = raw.trim().toUpperCase();
  return /^[A-Z]{2}$/.test(code) ? code : "";
}
