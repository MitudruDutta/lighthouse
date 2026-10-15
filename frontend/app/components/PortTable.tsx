"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import type { PortRow } from "../lib/api";
import { Badge, Empty, number } from "./ui";

export function PortTable({ ports, unusual }: { ports: PortRow[]; unusual: Record<string, string> }) {
  const [query, setQuery] = useState("");
  const [signalsOnly, setSignalsOnly] = useState(false);
  const [sort, setSort] = useState("calls");
  const found = ports.filter((p) => (!signalsOnly || p.key in unusual) && `${p.name ?? ""} ${p.country ?? ""} ${p.key}`.toLowerCase().includes(query.toLowerCase().trim())).sort((a, b) => sort === "name" ? (a.name ?? a.key).localeCompare(b.name ?? b.key) : Number(b[sort as keyof PortRow] ?? -1) - Number(a[sort as keyof PortRow] ?? -1));
  return <>
    <div className="mb-5 flex flex-wrap items-center gap-3"><label className="workspace-search min-w-0 flex-1 basis-full sm:basis-60"><Search size={15} aria-hidden /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter these ports by name or country…" aria-label="Filter listed ports" /></label><select aria-label="Sort listed ports" value={sort} onChange={(event) => setSort(event.target.value)} className="!text-xs"><option value="calls">Most port calls</option><option value="import_tonnes">Most cargo unloaded</option><option value="export_tonnes">Most cargo loaded</option><option value="name">Name A–Z</option></select><label className="flex items-center gap-2 text-xs text-muted"><input type="checkbox" checked={signalsOnly} onChange={(event) => setSignalsOnly(event.target.checked)} />Unusual only</label></div>
    <p className="mb-3 text-[11px] text-faint" aria-live="polite">{found.length} of {ports.length} loaded ports shown{ports.length === 200 ? " · Showing the busiest 200. Select a country above to narrow coverage." : ""}</p>
    {!found.length ? <Empty>No listed ports match these filters. Try a country above or search memory for another port.</Empty> : <div><p className="mb-3 text-[11px] text-faint xl:hidden">Scroll sideways for traffic and cargo →</p><div className="overflow-x-auto" role="region" aria-label="Port activity" tabIndex={0}><table className="grid ports-table"><thead><tr><th>Port</th><th>Country</th><th className="num">Port calls</th><th className="num">Container</th><th className="num">Tanker</th><th className="num">Dry bulk</th><th className="num">Unloaded (t)</th><th className="num">Loaded (t)</th></tr></thead><tbody>{found.map((p) => <tr key={p.key}><td><Link href={`/ports/${encodeURIComponent(p.key)}`} className="link font-medium">{p.name ?? p.key}</Link>{p.key in unusual ? <span className="ml-2"><Badge tone="busy">unusual</Badge></span> : null}<div className="mt-1 text-[10px] text-faint">{p.key}</div></td><td className="text-muted">{p.country ?? "—"}</td><td className="num font-medium">{number(p.calls)}</td><td className="num">{number(p.calls_container)}</td><td className="num">{number(p.calls_tanker)}</td><td className="num">{number(p.calls_dry_bulk)}</td><td className="num">{number(p.import_tonnes)}</td><td className="num">{number(p.export_tonnes)}</td></tr>)}</tbody></table></div></div>}
  </>;
}
