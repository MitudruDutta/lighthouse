"use client";

import { ArrowDown, ArrowLeft, ArrowRight, ArrowUpRight, Check, ChevronDown, Focus, GitBranch, LocateFixed, Route, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type { ConnectionStep, GraphNode, Network } from "../lib/api";
import { ENTITY_KINDS, nodeTitle, refTitle } from "../lib/investigation";
import { Badge, Prose, RefLink, When, href } from "./ui";
import { agentName } from "./words";

const COLORS: Record<string, string> = { Episode: "var(--violet)", Entry: "var(--sky)", Port: "var(--sky)", PortCall: "var(--coral)", Berth: "var(--beam)", Vessel: "var(--mint)", Lesson: "var(--violet)", Playbook: "var(--violet)" };
type Endpoint = { kind: string; key: string };
export type TraceQuery = {
  kind: string;
  key: string;
  from: Endpoint;
  to: Endpoint;
  steps?: ConnectionStep[] | null;
};

function EndpointFields({ side, value, onChange, nodes }: {
  side: "From" | "To";
  value: Endpoint;
  onChange: (value: Endpoint) => void;
  nodes: GraphNode[];
}) {
  const list = `trace-${side.toLowerCase()}-keys`;
  return <fieldset className="trace-endpoint">
    <legend><span>{side === "From" ? "01" : "02"}</span>{side === "From" ? "Start entity" : "Destination"}</legend>
    <div className="trace-endpoint-fields">
      <label><span>Entity type</span><select name={`${side.toLowerCase()}_kind`} value={value.kind} onChange={(event) => onChange({ kind: event.target.value, key: "" })} aria-label={`${side} entity type`}>{ENTITY_KINDS.map((kind) => <option key={kind}>{kind}</option>)}</select></label>
      <label><span>Entity key</span><input name={`${side.toLowerCase()}_key`} value={value.key} onChange={(event) => onChange({ ...value, key: event.target.value })} list={list} aria-label={`${side} entity key`} placeholder="Choose or enter a key" maxLength={300} required autoComplete="off" /></label>
    </div>
    <datalist id={list}>{nodes.filter((node) => node.ref[0] === value.kind).map((node) => <option key={node.id} value={String(node.ref[1])}>{nodeTitle(node)}</option>)}</datalist>
  </fieldset>;
}

export function NetworkView({ network, trace }: { network: Network; trace: TraceQuery }) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [from, setFrom] = useState(trace.from);
  const [to, setTo] = useState(trace.to);
  const [assigned, setAssigned] = useState("");
  const canvas = useRef<HTMLDivElement>(null);
  const root = network.nodes.find((node) => node.id === network.focus) ?? network.nodes[0];
  const selected = network.nodes.find((node) => node.id === selectedId) ?? root;
  const others = network.nodes.filter((node) => node.id !== root?.id);
  const height = Math.max(420, Math.ceil(others.length / 2) * 72 + 90);
  const position = new Map<number, { x: number; y: number }>(root ? [[root.id, { x: 500, y: height / 2 }]] : []);
  others.forEach((node, i) => position.set(node.id, { x: i % 2 ? 830 : 170, y: (height - Math.ceil(others.length / 2) * 72) / 2 + 36 + Math.floor(i / 2) * 72 }));
  const connected = network.edges.filter((edge) => edge.source === selected?.id || edge.target === selected?.id);
  const nodeById = new Map(network.nodes.map((node) => [node.id, node]));
  const isEntity = selected && ENTITY_KINDS.includes(selected.ref[0]);
  const changed = from.kind !== trace.from.kind || from.key !== trace.from.key || to.kind !== trace.to.kind || to.key !== trace.to.key;
  const steps = changed ? undefined : trace.steps;

  useEffect(() => {
    const chart = canvas.current;
    if (!chart) return;
    const center = () => {
      chart.scrollLeft = (chart.scrollWidth - chart.clientWidth) / 2;
      chart.scrollTop = (chart.scrollHeight - chart.clientHeight) / 2;
    };
    const observer = new ResizeObserver(center);
    observer.observe(chart);
    center();
    return () => observer.disconnect();
  }, [network.focus]);

  function assign(side: "start" | "destination") {
    if (!selected || !isEntity) return;
    const value = { kind: selected.ref[0], key: String(selected.ref[1]) };
    if (side === "start") setFrom(value); else setTo(value);
    setAssigned(`${nodeTitle(selected)} selected as ${side}.`);
  }

  return <div className="investigation-workbench">
    {root && selected ? <div className="network-workspace">
      <section className="network-stage" aria-label="Connected evidence">
        <header className="network-stage-header"><div><span className="eyebrow">01 / Explore</span><h2><GitBranch size={17} aria-hidden />Connected evidence</h2></div><span className="network-count">{network.nodes.length} nodes<span> / </span>{network.edges.length} relations</span></header>
        <div ref={canvas} className="network-canvas" tabIndex={0} aria-label="Scrollable graph. Select a node to inspect it.">
          <svg viewBox={`0 0 1000 ${height}`} style={{ height: Math.max(380, height * .78) }} role="group" aria-label="Interactive entity neighbourhood. Select a node to inspect its evidence.">
            <defs><pattern id="graph-dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="var(--chart-grid)" /></pattern><marker id="edge-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="var(--sky)" /></marker></defs><rect width="1000" height={height} fill="url(#graph-dots)" />
            {network.edges.map((edge) => {
              const a = position.get(edge.source)!; const b = position.get(edge.target)!;
              const direction = b.x > a.x ? 1 : -1;
              const x1 = a.x + 104 * direction; const x2 = b.x - 108 * direction;
              const active = edge.source === selected.id || edge.target === selected.id;
              return <g key={edge.id}><path d={`M${x1},${a.y} C${(x1 + x2) / 2},${a.y} ${(x1 + x2) / 2},${b.y} ${x2},${b.y}`} fill="none" stroke={active ? "var(--sky)" : "var(--edge-2)"} strokeWidth={active ? 1.7 : 1} opacity={active ? .8 : .3} markerEnd="url(#edge-arrow)" /><text x={(x1 + x2) / 2} y={(a.y + b.y) / 2 - 6} fontSize="10" fill="var(--ink-3)" textAnchor="middle" paintOrder="stroke" stroke="var(--chart-sea)" strokeWidth="4">{edge.type}</text></g>;
            })}
            {network.nodes.map((node) => {
              const p = position.get(node.id)!; const color = COLORS[node.ref[0]] ?? "var(--sky)";
              const title = nodeTitle(node);
              return <g key={node.id} transform={`translate(${p.x},${p.y})`} role="button" tabIndex={0} aria-label={`Inspect ${node.ref[0]} ${title}`} aria-pressed={selected.id === node.id} onClick={() => setSelectedId(node.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedId(node.id); } }} className="network-node"><title>{`${title} · ${String(node.ref[1])}`}</title><rect x="-105" y="-26" width="210" height="52" rx="8" fill={node.id === root.id ? "var(--info-bg)" : "var(--panel)"} stroke={selected.id === node.id ? color : "var(--edge-2)"} strokeWidth={selected.id === node.id ? 2 : 1} /><circle cx="-89" cy="-8" r="3" fill={color} /><text x="-79" y="-4" fill="var(--ink-3)" fontSize="9">{node.ref[0].toUpperCase()}{node.id === root.id ? " / FOCUS" : ""}</text><text x="-89" y="16" fill="var(--ink)" fontSize="13" fontWeight="500">{title.length > 25 ? `${title.slice(0, 24)}…` : title}</text></g>;
            })}
          </svg>
        </div>
        <footer className="network-legend"><div>{[...new Set(network.nodes.map((node) => node.ref[0]))].map((kind) => <span key={kind}><i style={{ background: COLORS[kind] }} />{kind}</span>)}</div><p>{network.limited ? "Select a neighbour to explore beyond this view." : "Select any node to inspect its evidence."}</p></footer>
      </section>
      <aside className="entity-panel" aria-label="Entity inspector" aria-live="polite">
        <header className="entity-panel-header"><span className="eyebrow">Selected entity</span><LocateFixed size={15} aria-hidden /></header>
        <div className="entity-summary">
          <div className="flex flex-wrap items-center gap-2"><Badge tone="observation">{selected.ref[0]}</Badge>{selected.state ? <Badge tone={selected.state}>{selected.state}</Badge> : null}</div>
          <h2>{nodeTitle(selected)}</h2>
          {selected.at || selected.by ? <dl className="entity-metadata">{selected.at ? <div><dt>Recorded</dt><dd><When at={selected.at} /></dd></div> : null}{selected.by ? <div><dt>By</dt><dd>{agentName(selected.by)}</dd></div> : null}</dl> : null}
          <details className="entity-identifier"><summary>Record identifier<ChevronDown size={12} aria-hidden /></summary><code>{String(selected.ref[1])}</code></details>
          {selected.description ? <div className="entity-description"><Prose text={selected.description} /></div> : null}
          <div className="entity-actions">{href(selected.ref) ? <RefLink refer={selected.ref}><span>Open full record<ArrowUpRight size={13} aria-hidden /></span></RefLink> : null}{selected.id !== root.id ? <Link href={`/investigate?kind=${selected.ref[0]}&key=${encodeURIComponent(String(selected.ref[1]))}`} className="button-quiet"><Focus size={13} aria-hidden />Explore this node</Link> : null}</div>
          {isEntity ? <div className="entity-trace-actions"><span>Trace from this entity</span><div><button type="button" onClick={() => assign("start")}><Route size={12} aria-hidden />Use as start</button><button type="button" onClick={() => assign("destination")}><ArrowRight size={12} aria-hidden />Use as destination</button></div></div> : null}
        </div>
        <section className="entity-relations"><header><h3>Connections</h3><span>{connected.length}</span></header><ul>{connected.map((edge) => {
          const other = nodeById.get(edge.source === selected.id ? edge.target : edge.source)!;
          return <li key={edge.id}><button type="button" className="relation-item" onClick={() => setSelectedId(other.id)}><i style={{ background: COLORS[other.ref[0]] }} /><span><small>{other.ref[0]} · {edge.source === selected.id ? "Outgoing" : "Incoming"} {edge.type.replaceAll("_", " ")}</small><strong>{nodeTitle(other)}</strong></span><ArrowUpRight size={13} aria-hidden /></button></li>;
        })}</ul>{!connected.length ? <p className="text-xs text-faint">No connections in this view.</p> : null}</section>
      </aside>
    </div> : <div className="card py-14 text-center"><Search size={27} className="mx-auto mb-4 text-faint" aria-hidden /><h2 className="text-base font-semibold">No entity found</h2><p className="mt-2 text-sm text-muted">Choose another key, or wait for the first import.</p></div>}

    <section className="trace-workspace" aria-label="Trace a connection">
      <header className="trace-header"><div className="trace-title"><span><Route size={20} aria-hidden /></span><div><p className="eyebrow">02 / Trace</p><h2>Find the path between two entities</h2></div></div><span className="trace-limit">Up to 6 hops</span></header>
      <p className="trace-intro">Start with two records. Follow the shortest known chain and see which relationships still hold.</p>
      <form action="/investigate" className="trace-form"><input type="hidden" name="kind" value={trace.kind} /><input type="hidden" name="key" value={trace.key} />
        <div className="trace-endpoints"><EndpointFields side="From" value={from} onChange={setFrom} nodes={network.nodes} /><span className="trace-bridge" aria-hidden><ArrowRight size={18} /><ArrowDown size={18} /></span><EndpointFields side="To" value={to} onChange={setTo} nodes={network.nodes} /></div>
        <div className="trace-submit"><p role="status">{assigned || "Tip: select a graph node to use it as a start or destination."}</p><button type="submit"><Route size={15} aria-hidden />Trace path</button></div>
      </form>
      <div className="trace-results" aria-live="polite">
        {steps === undefined ? <div className="trace-placeholder"><GitBranch size={19} aria-hidden /><p>Your connection appears here.<span>Each hop keeps its direction, source date and current status.</span></p></div> : steps === null ? <div className="trace-placeholder"><Search size={20} aria-hidden /><p>No chain found within six hops.<span>Try records sharing a port or berth, or check the entity keys.</span></p></div> : !steps.length ? <div className="trace-placeholder"><Check size={20} aria-hidden /><p>Both ends refer to the same entity.<span>No hops needed.</span></p></div> : <>
          <header className="trace-result-header"><span><Check size={14} aria-hidden />Connection found</span><span>{steps.length} {steps.length === 1 ? "hop" : "hops"}</span></header>
          <ol className="trace-steps">{steps.map((step, i) => <li key={i}><span className="trace-step-number">{String(i + 1).padStart(2, "0")}</span><div className="trace-step-content"><div className="trace-step-relation"><span>{step.forward ? <ArrowRight size={13} aria-hidden /> : <ArrowLeft size={13} aria-hidden />}{step.relation.replaceAll("_", " ")}</span><Badge tone={step.current ? "closed" : "quiet"}>{step.current ? "Current" : "Historical"}</Badge>{step.since ? <span className="trace-step-date">Since <When at={step.since} /></span> : null}</div><div className="trace-step-entities"><RefLink refer={step.from}><small>{step.from[0]}</small><strong>{refTitle(step.from, network.nodes)}</strong></RefLink><ArrowRight size={15} aria-hidden /><RefLink refer={step.to}><small>{step.to[0]}</small><strong>{refTitle(step.to, network.nodes)}</strong></RefLink></div></div></li>)}</ol>
          <p className="trace-history-note">Historical relationships may appear in the chain. A connection shows shared evidence; it does not establish a common cause.</p>
        </>}
      </div>
    </section>
  </div>;
}
