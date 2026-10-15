import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Lighthouse",
  description: "Ports of the world and the agents that watch them, on a graph memory.",
};

const LINKS = [
  ["/", "Overview"],
  ["/ports", "World ports"],
  ["/berths", "Finnish berths"],
  ["/episodes", "Episodes"],
  ["/learned", "Learned"],
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full">
        <header className="border-b" style={{ borderColor: "var(--line)", background: "var(--panel)" }}>
          <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
            <Link href="/" className="text-base font-semibold tracking-tight">
              Lighthouse
            </Link>
            <nav className="nav flex flex-wrap gap-1">
              {LINKS.map(([to, label]) => (
                <Link key={to} href={to}>
                  {label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-faint">
          Port calls of Finland: Fintraffic / digitraffic.fi, CC BY 4.0. Ports of the world: Source: IMF PortWatch.
        </footer>
      </body>
    </html>
  );
}
