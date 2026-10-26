import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RFQ Assistant — Industrial Quotation Preparation Workbench",
  description:
    "Human-reviewed RFQ intake and quotation preparation assistant for independent industrial and electronic component distributors.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
