import type { Metadata } from "next";
import { Suspense } from "react";

import { BerthBoard } from "@/app/components/BerthBoard";
import { Loading } from "@/app/components/ui";
import { type Berth, api } from "@/app/lib/api";

export const metadata: Metadata = { title: "Berth board" };

export default function Berths() {
  return <div className="grid gap-6"><div><p className="eyebrow mb-3">Operations / Finland</p><h1 className="display">The berth board<span className="text-[var(--sky)]">.</span></h1><p className="mt-2 max-w-[70ch] text-sm text-muted">See where expected ship arrivals exceed the overlap seen before. Find a berth, inspect its history, and follow the port calls behind each signal.</p></div><Suspense fallback={<Loading what="the berth board" />}><Board /></Suspense></div>;
}

async function Board() {
  return <BerthBoard berths={await api<Berth[]>("/api/berths")} />;
}
