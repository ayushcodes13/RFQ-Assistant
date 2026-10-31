import type { Metadata } from "next";
import LandingPage from "@/components/LandingPage";

export const metadata: Metadata = {
  title: "RFQ Assistant — See the work behind every quote",
  description:
    "Prepare industrial quotations with editable RFQ lines, exact manufacturer and part-number matching, source references, and human review.",
};

export default function MarketingHome() {
  return <LandingPage />;
}
