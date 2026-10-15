import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "./marketing.css";
const sans = Geist({ subsets: ["latin"], variable: "--font-sans" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" });
export const metadata: Metadata = {
  title: {
    default: "Lighthouse Memory — A past to build on",
    template: "%s · Lighthouse Memory",
  },
  description:
    "Connected, versioned memory for agents. Store facts, follow their history, and coordinate through FalkorDB.",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <a href="#main" className="skip">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
