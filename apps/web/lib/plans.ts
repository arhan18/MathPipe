import type { PricingTier } from "@/components/ui/pricing-cards";

// Draft quotas per PRD §29 + architecture §25. Prices are placeholders
// finalized with billing in Phase 9. Quotas are config, not promises.
export const TIERS: PricingTier[] = [
  {
    name: "Free",
    price: 0,
    interval: "forever",
    description: "Try the magic on a real document.",
    features: [
      { name: "10 pages / month", included: true },
      { name: "Standard conversion", included: true },
      { name: "Native editable equations", included: true },
      { name: "AI verification", included: false },
      { name: "Batch conversion", included: false },
    ],
    cta: { text: "Convert free", href: "/convert" },
  },
  {
    name: "Pro",
    price: 12,
    interval: "monthly",
    description: "For teachers, tutors and students.",
    highlight: true,
    features: [
      { name: "500 pages / month", included: true },
      { name: "50 verified pages / month", included: true },
      { name: "Priority processing", included: true },
      { name: "Conversion history", included: true },
      { name: "Batch conversion", included: false },
    ],
    cta: { text: "Go Pro", href: "/signup" },
  },
  {
    name: "Power",
    price: 29,
    interval: "monthly",
    description: "For heavy educators and creators.",
    features: [
      { name: "1,500 pages / month", included: true },
      { name: "150 verified pages / month", included: true },
      { name: "Priority processing", included: true },
      { name: "Batch conversion", included: true },
      { name: "API access", included: false },
    ],
    cta: { text: "Go Power", href: "/signup" },
  },
  {
    name: "Business",
    price: 99,
    interval: "monthly",
    description: "For publishers, EdTech and teams.",
    features: [
      { name: "5,000+ pages / month", included: true },
      { name: "500+ verified pages / month", included: true },
      { name: "Team workspace", included: true },
      { name: "Batch + API access", included: true },
      { name: "Dedicated support", included: true },
    ],
    cta: { text: "Contact sales", href: "/contact" },
  },
];
