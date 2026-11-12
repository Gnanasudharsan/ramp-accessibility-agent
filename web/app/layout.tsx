import type { Metadata } from "next";
import { Atkinson_Hyperlegible_Mono, Atkinson_Hyperlegible_Next } from "next/font/google";

import { SiteFooter, SiteHeader } from "@/components/SiteHeader";

import "./globals.css";

const sans = Atkinson_Hyperlegible_Next({ subsets: ["latin"], variable: "--font-atkinson", display: "swap", adjustFontFallback: false });
const mono = Atkinson_Hyperlegible_Mono({ subsets: ["latin"], variable: "--font-atkinson-mono", display: "swap", adjustFontFallback: false });

export const metadata: Metadata = {
  title: { default: "Ramp — agentic accessibility auditor", template: "%s · Ramp" },
  description:
    "Ramp finds accessibility barriers on a website, writes the fix, and proves it works. Measured on a public benchmark.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <SiteHeader />
        <main id="main" tabIndex={-1} className="mx-auto max-w-5xl px-4 pt-12 focus:outline-none">
          {children}
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
