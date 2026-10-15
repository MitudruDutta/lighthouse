"use client";

import { Search, Ship } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import type { Berth } from "../lib/api";
import { segments } from "../lib/api";
import { Badge, Empty, When } from "./ui";

export function BerthBoard({ berths }: { berths: Berth[] }) {
  const [query, setQuery] = useState("");
  const [onlySignals, setOnlySignals] = useState(false);
  const signals = berths.filter((b) => b.overload).length;
  const found = berths.filter((b) => (!onlySignals || b.overload) && `${b.name ?? ""} ${b.berth} ${b.area ?? ""}`.toLowerCase().includes(query.toLowerCase().trim()));
  return <section className="card">
    <header className="mb-5 flex flex-wrap items-center justify-between gap-4"><div><h2 className="flex items-center gap-2 text-sm font-semibold"><Ship size={17} className="text-[var(--sky)]" aria-hidden />Berth board</h2><p className="mt-1 text-xs text-faint">{berths.length} monitored · {signals} overload signals</p></div><label className="workspace-search w-full sm:w-64"><Search size={15} aria-hidden /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter berth, area or port code…" aria-label="Filter berths" /></label></header>
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3"><div role="group" aria-label="Berth filter" className="flex gap-1 rounded-lg bg-[var(--rule-soft)] p-1">{[false, true].map((signalsOnly) => <button type="button" key={String(signalsOnly)} aria-pressed={onlySignals === signalsOnly} onClick={() => setOnlySignals(signalsOnly)} className="!rounded-md !px-3 !py-2 !text-xs" style={{ background: onlySignals === signalsOnly ? "var(--panel)" : "transparent", color: "var(--ink)", boxShadow: onlySignals === signalsOnly ? "0 1px 3px #18312f12" : undefined }}>{signalsOnly ? `Overload signals (${signals})` : `All berths (${berths.length})`}</button>)}</div><p className="text-[11px] text-faint" aria-live="polite">{found.length} berths shown</p></div>
    {found.length ? <div><p className="mb-3 text-[11px] text-faint xl:hidden">Scroll sideways for overlap and supporting evidence →</p><div className="overflow-x-auto" role="region" aria-label="Berth activity" tabIndex={0}><table className="grid berths-table"><thead><tr><th>Berth / Port code</th><th>Area</th><th className="num">Highest observed overlap</th><th>Expected overlap</th><th>Evidence · port calls</th></tr></thead><tbody>{found.map((b) => <tr key={b.berth}><td><Link href={`/berths/${segments(b.berth)}`} className="link font-medium">{b.name ?? b.berth}</Link><div className="mt-1 text-[10px] text-faint">{b.berth}</div></td><td className="text-muted">{b.area ?? "—"}</td><td className="num font-medium">{b.capacity}</td><td>{b.overload ? <><Badge tone="busy">{b.overload.most} expected at once</Badge><div className="mt-1 text-[10px] text-muted"><When at={b.overload.from} /><span className="block">{b.overload.until ? <>Until <When at={b.overload.until} /></> : "End time not yet known"}</span></div></> : <Badge tone="closed">Within observed overlap</Badge>}</td><td>{b.overload ? <div className="flex flex-wrap gap-2">{b.overload.calls.map((id) => <Link key={id} href={`/portcalls/${id}`} className="link text-xs">{id}</Link>)}</div> : <span className="text-faint">—</span>}</td></tr>)}</tbody></table></div></div> : <Empty>No berths match. Try a different name or show all berths.</Empty>}
    <p className="mt-4 border-t border-[var(--edge)] pt-4 text-[11px] leading-relaxed text-faint">An overload signal compares expected overlap with the highest overlap previously observed. It is a prompt to investigate; the feed does not publish a berth’s physical capacity.</p>
  </section>;
}
