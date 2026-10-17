import { CheckCircle2, CloudDownload, Database, Globe2, Radio, ShieldCheck, Ship, TriangleAlert } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Badge, Card, Loading, When, ago, number } from "@/app/components/ui";
import { type Quality, type Status, type World, maybe } from "@/app/lib/api";
import { isFresh, utcTime } from "@/app/lib/freshness";

export const metadata: Metadata = { title: "Data sources" };

export default function Sources() {
  return <div className="grid gap-6">
    <header><p className="eyebrow mb-3">Workspace / Data</p><h1 className="display">Know your sources<span className="text-[var(--sky)]">.</span></h1><p className="mt-2 max-w-[66ch] text-sm text-muted">Understand where your evidence comes from, how current it is, and what it covers.</p></header>
    <Suspense fallback={<Loading what="source health" />}><Health /></Suspense>
    <Suspense fallback={<Loading what="data coverage" />}><Coverage /></Suspense>
  </div>;
}

async function Coverage() {
  const quality = await maybe<Quality>("/api/quality");
  if (!quality) return <Card title="Data coverage"><p className="text-sm text-muted">Coverage metrics are temporarily unavailable. Please check again shortly.</p></Card>;
  const rows = [
    ["Ports with mapped coordinates", quality.ports.located, quality.ports.total],
    ["Ports with daily activity", quality.ports.daily_counts, quality.ports.total],
    ["Port calls with a berth", quality.calls.with_berth, quality.calls.total],
    ["Port calls with an expected arrival", quality.calls.with_eta, quality.calls.total],
    ["Port calls with an actual arrival", quality.calls.with_actual_arrival, quality.calls.total],
  ] as const;
  return <Card title="Coverage you can inspect" aside="Read from the stored graph">
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_1fr]">
      <div className="grid gap-5">{rows.map(([label, count, total]) => <div key={label}>
        <div className="flex justify-between gap-3 text-xs"><span>{label}</span><span className="tabular text-muted">{number(count)} / {number(total)}</span></div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--rule-soft)]" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={Math.max(1, total)} aria-valuenow={count}><div className="h-full rounded-full bg-[var(--sky)]" style={{ width: `${total ? count / total * 100 : 0}%` }} /></div>
      </div>)}</div>
      <div className="rounded-lg bg-[var(--rule-soft)] p-4"><p className="eyebrow">Memory & source limits</p>
        <dl className="mt-4 grid gap-4 text-xs">
          <div className="flex justify-between gap-3"><dt className="text-muted">Stored entity versions</dt><dd className="tabular font-semibold">{number(quality.versions)}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-muted">PortWatch ports joined by UN/LOCODE</dt><dd className="tabular font-semibold">{number(quality.ports.joined_by_locode)}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-muted">Calls reporting multiple areas</dt><dd className="tabular font-semibold">{number(quality.calls.multiple_areas)}</dd></div>
        </dl><p className="mt-4 text-[10px] leading-relaxed text-faint">Only the first reported port area is currently mapped. Missing values stay unknown; charts do not treat them as quiet days.</p>
      </div>
    </div>
  </Card>;
}

function Receipts({ values }: { values?: Record<string, number> }) {
  const rows = Object.entries(values ?? {}).filter(([status]) => ["created", "changed", "inserted", "unchanged"].includes(status));
  if (!rows.length) return <p className="py-4 text-xs text-faint">No new observations in the last update.</p>;
  const labels: Record<string, string> = { created: "New observations", changed: "Updated observations", inserted: "Added to history", unchanged: "Already in memory" };
  return <dl>{rows.map(([status, count]) => <div key={status} className="source-receipt"><span className="h-1.5 w-1.5 rounded-full bg-[var(--mint)]" aria-hidden /><dt className="flex-1">{labels[status]}</dt><dd className="tabular font-medium">{number(count)}</dd></div>)}</dl>;
}

async function Health() {
  const [status, world] = await Promise.all([maybe<Status>("/api/status"), maybe<World>("/api/world")]);
  if (!status) return <Card title="Updates temporarily unavailable"><p className="text-sm text-muted">Please check again shortly. Previously saved evidence remains in memory.</p></Card>;
  const now = utcTime(status.now);
  const feed = status.last_poll;
  const global = status.last_world_poll;
  const feedFresh = isFresh(feed?.at, status.now, 15) && status.availability.feed;
  const globalFresh = isFresh(global?.at, status.now, 90) && status.availability.portwatch;
  const lag = world?.newest_day ? Math.max(0, Math.floor((utcTime(status.now.slice(0, 10)) - utcTime(world.newest_day)) / 86_400_000)) : null;
  return <>
    <section className="card flex flex-wrap items-center gap-4 !bg-[var(--info-bg)]" aria-label="Import summary">
      {feedFresh && globalFresh ? <CheckCircle2 size={22} className="text-[var(--mint)]" aria-hidden /> : <TriangleAlert size={22} className="text-[var(--coral)]" aria-hidden />}
      <div className="flex-1"><h2 className="text-sm font-semibold">{feedFresh && globalFresh ? "Both sources checked recently" : "Some source updates are delayed"}</h2><p className="mt-1 text-xs text-muted">Check times show when Lighthouse connected; observation dates show how current the source data is. Always check the evidence date before acting.</p></div><span className="text-[10px] text-faint">Snapshot <When at={status.now} /></span>
    </section>
    <div className="grid items-start gap-6 lg:grid-cols-2">
      <Card>
        <header className="flex items-start justify-between gap-3"><div className="flex items-center gap-3"><span className="rounded-lg bg-[var(--info-bg)] p-2.5 text-[var(--sky)]"><Ship size={20} aria-hidden /></span><div><h2 className="text-base font-semibold">Finnish ship arrivals</h2><p className="mt-0.5 text-xs text-faint">Fintraffic · Digitraffic</p></div></div><Badge tone={feedFresh ? "closed" : "busy"}>{!feed ? "Awaiting data" : feedFresh ? "Connected" : "Updates delayed"}</Badge></header>
        <dl className="my-6 grid grid-cols-2 gap-x-4 gap-y-5 text-xs"><div><dt className="text-faint">Last completed update</dt><dd className="mt-1 font-medium">{ago(feed?.at, now)}</dd></div><div><dt className="text-faint">Usual check cadence</dt><dd className="mt-1 font-medium">Every 5 minutes</dd></div><div className="col-span-2"><dt className="text-faint">Feed updated</dt><dd className="mt-1"><When at={feed?.feed_time} /></dd></div></dl>
        {!feedFresh ? <p className="mb-4 rounded-lg bg-[var(--warn-bg)] p-3 text-xs text-[var(--coral)]">New arrivals may take longer to appear. Check observation times when reviewing a berth.</p> : null}
        <h3 className="eyebrow border-t border-[var(--edge)] pt-4">Latest observations</h3><Receipts values={feed?.port_calls} />
        <div className="mt-4 rounded-lg bg-[var(--rule-soft)] p-3 text-xs leading-relaxed text-muted">Arrivals, departures, vessel details and berth assignments. Personal fields are dropped before storage. Existing versions remain in history.</div>
        <div className="mt-5 flex justify-between gap-3 text-xs"><Link href="/berths" className="link">Open berth board →</Link><a href="https://meri.digitraffic.fi/api/port-call/v1/port-calls" className="link" target="_blank" rel="noreferrer">Source feed ↗</a></div>
      </Card>
      <Card>
        <header className="flex items-start justify-between gap-3"><div className="flex items-center gap-3"><span className="rounded-lg bg-[var(--learn-bg)] p-2.5 text-[var(--violet)]"><Globe2 size={20} aria-hidden /></span><div><h2 className="text-base font-semibold">Global port activity</h2><p className="mt-0.5 text-xs text-faint">IMF · PortWatch</p></div></div><Badge tone={globalFresh ? "closed" : "busy"}>{!global ? "Awaiting data" : global.state === "running" || global.state === "updating" ? "Updating" : globalFresh ? "Checked" : "Updates delayed"}</Badge></header>
        <dl className="my-6 grid grid-cols-2 gap-x-4 gap-y-5 text-xs"><div><dt className="text-faint">Latest source check</dt><dd className="mt-1 font-medium">{ago(global?.at, now)}</dd></div><div><dt className="text-faint">Usual check cadence</dt><dd className="mt-1 font-medium">Hourly</dd></div><div><dt className="text-faint">Latest observation day</dt><dd className="mt-1 font-medium"><When at={world?.newest_day} day />{lag !== null ? <span className="mt-1 block text-[10px] font-normal text-faint">{lag === 0 ? "Today’s source data" : `${lag} days behind today · source publication delay`}</span> : null}</dd></div><div><dt className="text-faint">Days added this update</dt><dd className="mt-1 font-medium">{global ? global.days.length : "—"}</dd></div></dl>
        {!globalFresh ? <p className="mb-4 rounded-lg bg-[var(--warn-bg)] p-3 text-xs text-[var(--coral)]">New activity may take longer to appear. The latest available observation date is shown above.</p> : null}
        <h3 className="eyebrow border-t border-[var(--edge)] pt-4">Latest observations</h3><Receipts values={global?.rows} />
        <div className="mt-4 rounded-lg bg-[var(--rule-soft)] p-3 text-xs leading-relaxed text-muted">Daily calls by ship type and estimated cargo tonnes. Historical evidence remains available as new observations arrive.</div>
        <div className="mt-5 flex justify-between gap-3 text-xs"><Link href="/ports" className="link">Explore global ports →</Link><a href="https://portwatch.imf.org/" className="link" target="_blank" rel="noreferrer">Source website ↗</a></div>
      </Card>
    </div>
    <LiveSource status={status} now={now} />
    <div className="grid gap-4 sm:grid-cols-3">{[[Database, "Versioned memory", "A change adds history. The graph keeps what was true before."], [CloudDownload, "Automatic updates", "Scheduled feeds add new observations without replacing prior evidence."], [ShieldCheck, "Visible provenance", "Fintraffic: CC BY 4.0. IMF PortWatch: commercial reuse requires IMF permission."]].map(([Icon, title, description]) => { const Symbol = Icon as typeof Database; return <div key={String(title)} className="flex items-start gap-3 p-2"><Symbol size={18} className="mt-0.5 shrink-0 text-[var(--sky)]" aria-hidden /><div><h3 className="text-xs font-semibold">{String(title)}</h3><p className="mt-1 text-xs leading-relaxed text-faint">{String(description)}</p></div></div>; })}</div>
  </>;
}

/** Live ship positions: off until an administrator adds a key, then within minutes. */
function LiveSource({ status, now }: { status: Status; now: number }) {
  const live = status.last_ais;
  const fresh = !!live && isFresh(live.at, status.now, 35) && !!status.availability.ais;
  return (
    <Card>
      <header className="flex items-start justify-between gap-3"><div className="flex items-center gap-3"><span className="rounded-lg bg-[var(--good-bg)] p-2.5 text-[var(--mint)]"><Radio size={20} aria-hidden /></span><div><h2 className="text-base font-semibold">Live ship positions</h2><p className="mt-0.5 text-xs text-faint">AIS · aisstream.io</p></div></div><Badge tone={fresh ? "closed" : "busy"}>{!live ? "Off" : fresh ? "Live" : "Updates delayed"}</Badge></header>
      {live ? (
        <dl className="mt-6 grid grid-cols-2 gap-x-4 gap-y-5 text-xs sm:grid-cols-4"><div><dt className="text-faint">Last update</dt><dd className="mt-1 font-medium">{ago(live.at, now)}</dd></div><div><dt className="text-faint">Usual cadence</dt><dd className="mt-1 font-medium">Every 15 minutes</dd></div><div><dt className="text-faint">Ports watched</dt><dd className="mt-1 font-medium">{live.ports}</dd></div><div><dt className="text-faint">Cargo ships & tankers in port</dt><dd className="mt-1 font-medium">{live.ships_now}</dd></div></dl>
      ) : (
        <p className="mt-4 text-xs leading-relaxed text-muted">Off until an administrator adds an aisstream.io key. Then the busiest ports show the cargo ships and tankers in port within minutes, beside PortWatch&apos;s daily counts, which are published about a week later.</p>
      )}
      <div className="mt-5 flex justify-between gap-3 text-xs"><Link href="/ports" className="link">See ports in port now →</Link><a href="https://aisstream.io/" className="link" target="_blank" rel="noreferrer">Source website ↗</a></div>
    </Card>
  );
}
