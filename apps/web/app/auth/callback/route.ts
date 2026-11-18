import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

/** Only allow same-site relative paths as a post-login destination. */
function safeNext(value: string | null): string {
  if (!value) return "/dashboard";
  if (!value.startsWith("/") || value.startsWith("//")) return "/dashboard";
  return value;
}

function loginUrl(origin: string, message: string): URL {
  return new URL(`/login?error=${encodeURIComponent(message)}`, origin);
}

/**
 * PKCE callback for email confirmation, magic links, password recovery and
 * OAuth. Supabase redirects here with a one-time `code`, which must be
 * exchanged for a session and written to cookies on the response.
 */
export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const next = safeNext(url.searchParams.get("next"));
  const providerError =
    url.searchParams.get("error_description") ?? url.searchParams.get("error");

  if (providerError) {
    return NextResponse.redirect(
      loginUrl(url.origin, "That link is invalid or has expired. Sign in to request a new one."),
    );
  }
  if (!code) {
    return NextResponse.redirect(
      loginUrl(url.origin, "Missing confirmation code. Open the link from your email again."),
    );
  }

  const response = NextResponse.redirect(new URL(next, url.origin));
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (cookiesToSet) => {
          for (const { name, value, options } of cookiesToSet) {
            response.cookies.set(name, value, options);
          }
        },
      },
    },
  );

  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    return NextResponse.redirect(
      loginUrl(url.origin, "Could not complete sign in. The link may have expired."),
    );
  }

  return response;
}
