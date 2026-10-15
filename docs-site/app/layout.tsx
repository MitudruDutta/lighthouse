import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { DocsShell } from "@/components/docs-shell";
import "./globals.css";
const sans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-mono", subsets: ["latin"] });
export const metadata: Metadata = {
  title: { default: "Lighthouse Memory", template: "%s · Lighthouse Memory" },
  description:
    "Versioned graph memory, evidence, recall, and agent coordination on FalkorDB.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${sans.variable} ${mono.variable}`}
    >
      <body>
        <a href="#article" className="skip">
          Skip to content
        </a>
        <DocsShell>{children}</DocsShell>
      </body>
    </html>
  );
}
