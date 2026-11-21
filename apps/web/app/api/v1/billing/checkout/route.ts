import { newRequestId } from "@mathpipe/shared";
import { requireUser, checkLimit, apiError } from "@/lib/api";

export const runtime = "nodejs";

const PLAN_ENV: Record<string, string> = {
  pro: "DODO_PRODUCT_PRO",
  power: "DODO_PRODUCT_POWER",
};

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://mathpipe.arhanahmad.com";

/**
 * POST /api/v1/billing/checkout — start a Dodo checkout session.
 *
 * Returns a hosted checkout URL. This route never grants entitlements: those
 * come only from verified webhooks, so a returning customer cannot fake a
 * plan by replaying a success redirect.
 */
export async function POST(req: Request) {
  const requestId = newRequestId();
  const limited = checkLimit(req, "jobs");
  if (!limited.ok) return limited.response;

  const auth = await requireUser();
  if ("response" in auth) return auth.response;

  const body = (await req.json().catch(() => null)) as { plan?: string } | null;
  const plan = body?.plan ?? "";
  const envName = PLAN_ENV[plan];
  if (!envName) {
    return apiError("INVALID_INPUT", "Unknown plan.", requestId);
  }

  if (!process.env.DODO_API_KEY) {
    return apiError("AUTH_NOT_CONFIGURED", "Checkout is not configured yet.", requestId);
  }

  const productId = process.env[envName];
  if (!productId) {
    return apiError(
      "INTERNAL",
      `Buying ${plan} is not open yet. No Dodo product is mapped for it.`,
      requestId,
    );
  }

  const base = process.env.DODO_API_BASE ?? "https://live.dodopayments.com";
  const res = await fetch(`${base}/checkouts`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.DODO_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      product_cart: [{ product_id: productId, quantity: 1 }],
      customer: auth.user.email ? { email: auth.user.email } : undefined,
      return_url: `${APP_URL}/checkout/success`,
      metadata: { user_id: auth.user.id, plan },
    }),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    console.error("checkout_session_failed", { requestId, plan, status: res.status, detail: detail.slice(0, 500) });
    return apiError("INTERNAL", "Could not start checkout. Please try again.", requestId);
  }

  const session = (await res.json()) as { checkout_url?: string | null };
  if (!session.checkout_url) {
    return apiError("INTERNAL", "Checkout did not return a payment link.", requestId);
  }

  return Response.json({ checkoutUrl: session.checkout_url });
}
