import { PricingCards } from "@/components/ui/pricing-cards";
import { TIERS } from "@/lib/plans";

export const metadata = { title: "Pricing" };

export default function PricingPage() {
  return (
    <>
      <div className="mx-auto max-w-5xl px-4 pt-16 text-center">
        <h1 className="font-display text-4xl">Simple, page-based pricing</h1>
        <p className="mt-2 text-neutral-400">
          Free tastes the magic. Paid plans scale with your teaching, studying, or publishing.
          Prices are launch drafts and lock at checkout.
        </p>
      </div>
      <PricingCards tiers={TIERS} className="md:grid-cols-2 lg:grid-cols-4" />
    </>
  );
}
