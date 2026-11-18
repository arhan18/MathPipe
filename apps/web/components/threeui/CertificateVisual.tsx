"use client";

import dynamic from "next/dynamic";

const EngravedCertificate = dynamic(
  () => import("@designcodeio/threeui/components/EngravedCertificate").then((m) => m.EngravedCertificate),
  { ssr: false, loading: () => <div className="h-full w-full animate-pulse rounded-xl bg-white/5" /> },
);

export function CertificateVisual() {
  return <EngravedCertificate mode="dark" />;
}
