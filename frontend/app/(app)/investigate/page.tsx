import { Network as NetworkIcon } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { NetworkView } from "@/app/components/NetworkView";
import { Loading } from "@/app/components/ui";
import { type ConnectionStep, type Network, api } from "@/app/lib/api";
import { ENTITY_KINDS } from "@/app/lib/investigation";

export const metadata: Metadata = { title: "Investigate" };
const FOCUS = ["Episode", ...ENTITY_KINDS, "Lesson", "Playbook", "Entry"];

export default function Investigate(props: PageProps<"/investigate">) {
  return <div className="grid gap-6">
    <header className="flex flex-wrap items-end justify-between gap-4"><div className="min-w-0 flex-1 basis-80"><p className="eyebrow mb-3">Intelligence / Connected evidence</p><h1 className="display">Follow the connections<span className="text-[var(--sky)]">.</span></h1><p className="mt-2 max-w-[72ch] text-sm text-muted">Explore the relationships behind an event. Trace how ships, port calls, berths, and shared memories connect.</p></div><Link href="/agents" className="button-quiet !text-xs">Agent control room ↗</Link></header>
    <Suspense fallback={<Loading what="connected evidence" />}><Body {...props} /></Suspense>
  </div>;
}

async function Body({ searchParams }: PageProps<"/investigate">) {
  const asked = await searchParams;
  const text = (name: string) => typeof asked[name] === "string" ? (asked[name] as string).slice(0, 300) : "";
  const kind = FOCUS.includes(text("kind")) ? text("kind") : "Episode";
  const key = text("key");
  const graph = await api<Network>("/api/network", { kind, key });
  const fromKind = ENTITY_KINDS.includes(text("from_kind")) ? text("from_kind") : "PortCall";
  const toKind = ENTITY_KINDS.includes(text("to_kind")) ? text("to_kind") : "PortCall";
  const calls = graph.nodes.filter((node) => node.ref[0] === "PortCall");
  const fromKey = text("from_key");
  const toKey = text("to_key");
  const result = fromKey && toKey ? await api<{ steps: ConnectionStep[] | null }>("/api/connection", { from_kind: fromKind, from_key: fromKey, to_kind: toKind, to_key: toKey, max_hops: 6 }) : null;
  return <>
    <form className="card grid grid-cols-[minmax(0,1fr)_auto] items-end gap-3 !py-4 sm:grid-cols-[140px_minmax(0,1fr)_auto]" action="/investigate">
      <label className="grid gap-1.5 text-xs text-muted">Focus type<select name="kind" defaultValue={kind}>{FOCUS.map((focus) => <option key={focus}>{focus}</option>)}</select></label>
      <label className="col-span-2 row-start-2 grid min-w-0 gap-1.5 text-xs text-muted sm:col-span-1 sm:row-start-auto">Entity key<input name="key" defaultValue={key} placeholder="Leave empty to explore the latest episode" maxLength={300} /></label>
      <button type="submit" className="col-start-2 row-start-1 inline-flex items-center gap-2 sm:col-start-3"><NetworkIcon size={15} aria-hidden />Explore</button>
    </form>
    <NetworkView key={`${kind}:${key}:${fromKind}:${fromKey}:${toKind}:${toKey}`} network={graph} trace={{
      kind, key,
      from: { kind: fromKind, key: fromKey || String(calls[0]?.ref[1] ?? "") },
      to: { kind: toKind, key: toKey || String(calls[1]?.ref[1] ?? "") },
      steps: result?.steps,
    }} />
  </>;
}
