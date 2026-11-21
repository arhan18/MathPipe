import type { PricingTier } from "@/components/ui/pricing-cards";

// Draft quotas per PRD §29 + architecture §25. Quotas are config, not promises.
// Prices are display data only: checkout grants entitlements from verified
// webhooks, never from the number rendered here.

export interface RegionPrices {
  symbol: string;
  currency: string;
  locale: string;
  pro: number;
  power: number;
  business: number;
}

const DEFAULT_PRICES: RegionPrices = {
  symbol: "$",
  currency: "USD",
  locale: "en-US",
  pro: 12,
  power: 29,
  business: 99,
};

// Purchasing-power pricing. Same limits as the default tier; nothing else
// changes. Keep this list small and intentional until real sales data exists.
const REGION_PRICES: Record<string, RegionPrices> = {
  IN: { symbol: "₹", currency: "INR", locale: "en-IN", pro: 199, power: 499, business: 1499 },
};

export function pricesForCountry(country: string): RegionPrices {
  return REGION_PRICES[country.toUpperCase()] ?? DEFAULT_PRICES;
}

export function tiersForCountry(country: string): PricingTier[] {
  const prices = pricesForCountry(country);
  return [
    {
      name: "Free",
      price: 0,
      priceSymbol: prices.symbol,
      priceLocale: prices.locale,
      interval: "forever",
      description: "Try the magic on a real document.",
      features: [
        { name: "10 pages / month", included: true },
        { name: "Standard conversion", included: true },
        { name: "Native editable equations", included: true },
        { name: "AI verification (coming soon)", included: false },
        { name: "Batch conversion", included: false },
      ],
      cta: { text: "Convert free", href: "/convert" },
    },
    {
      name: "Pro",
      price: prices.pro,
      priceSymbol: prices.symbol,
      priceLocale: prices.locale,
      interval: "monthly",
      description: "For teachers, tutors and students.",
      highlight: true,
      features: [
        { name: "500 pages / month", included: true },
        { name: "AI verification (coming soon)", included: false },
        { name: "Priority processing", included: true },
        { name: "Conversion history", included: true },
        { name: "Batch conversion", included: false },
      ],
      cta: { text: "Go Pro", href: "/signup" },
    },
    {
      name: "Power",
      price: prices.power,
      priceSymbol: prices.symbol,
      priceLocale: prices.locale,
      interval: "monthly",
      description: "For heavy educators and creators.",
      features: [
        { name: "1,500 pages / month", included: true },
        { name: "AI verification (coming soon)", included: false },
        { name: "Priority processing", included: true },
        { name: "Batch conversion", included: true },
      ],
      cta: { text: "Go Power", href: "/signup" },
    },
    {
      name: "Business",
      price: prices.business,
      priceSymbol: prices.symbol,
      priceLocale: prices.locale,
      interval: "monthly",
      description: "For publishers, EdTech and teams.",
      features: [
        { name: "5,000+ pages / month", included: true },
        { name: "AI verification (coming soon)", included: false },
        { name: "Batch conversion", included: true },
        { name: "Dedicated support", included: true },
      ],
      cta: { text: "Contact sales", href: "/contact" },
    },
  ];
}
