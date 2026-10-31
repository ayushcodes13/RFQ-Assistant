import type { Metadata } from "next";
import "@fontsource-variable/ibm-plex-sans";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource-variable/work-sans";
import "@fontsource/instrument-serif/400-italic.css";
import "./globals.css";
import "./landing.css";

export const metadata: Metadata = {
  title: "RFQ Assistant — See the work behind every quote",
  description:
    "Prepare industrial quotations with editable RFQ lines, exact manufacturer and part-number matching, source references, and human review.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}

