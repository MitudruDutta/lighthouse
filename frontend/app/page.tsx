import { ArrowRight, ArrowUpRight, Database, GitBranch, Globe2, Radar, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { HarborScene } from "./components/HarborScene";
import { AgentRelay, ConnectedDiagram, MemoryCards, MemoryTape, MotionCard } from "./components/LandingMotion";
import { Logo } from "./components/Logo";
import { WorldMap } from "./components/WorldMap";
import { Badge, When, number } from "./components/ui";
import { agentName, said } from "./components/words";
import { type Berth, type Episode, type EpisodeSummary, type Status, type World, maybe, segments } from "./lib/api";
import { docs } from "./lib/links";

export default function Landing() {
  return <div className="night landing-v2">
    <a href="#product" className="skip-link">Skip to product</a>
    <div className="landing-shell">
      <header className="landing-nav"><Link href="/" className="landing-brand"><Logo size={33} /><span>Lighthouse<span>.</span></span></Link><nav aria-label="Product navigation"><a href="#capabilities">The product</a><a href="#memory">The memory</a><Link href={docs()}>Documentation <ArrowUpRight size={12} aria-hidden /></Link></nav><Link href="/dashboard" className="button-quiet landing-nav-cta">Open workspace<ArrowUpRight size={13} aria-hidden /></Link></header>
      <main id="product">
        <section className="harbor-hero" aria-labelledby="landing-title">
          <div className="harbor-hero-copy"><p className="hero-kicker"><span />Intelligence for a connected world</p><h1 id="landing-title" className="display">See the signal.<br />Follow the <em>current.</em></h1><p className="hero-description">A port desk that connects the dots. Agents watch what changes, investigate the evidence, and remember what matters.</p><div className="hero-actions"><Link href="/dashboard" className="button">Explore the workspace<ArrowRight size={16} aria-hidden /></Link><Link href="/investigate" className="hero-secondary">Follow the evidence<ArrowUpRight size={14} aria-hidden /></Link></div><div className="hero-foundation"><GitBranch size={15} aria-hidden /><span>Connected data. Shared agent memory.</span><span className="falkor-tag">FalkorDB ↗</span></div></div>
          <HarborScene />
        </section>
        <Suspense fallback={<div className="landing-snapshot snapshot-loading">Reading the connected world…</div>}><Snapshot /></Suspense>
        <MemoryTape />
        <section id="capabilities" className="landing-section">
          <div className="landing-section-heading"><div><p className="hero-kicker">A clearer view. A smarter crew.</p><h2 className="display">Intelligence.<br /><em className="landing-mark">With a memory.</em></h2></div><p>From an unexpected arrival to a useful lesson. One place to see the change, follow the connections, and carry context forward.</p></div>
          <div className="product-bento">
            <MotionCard className="bento-world"><Suspense fallback={<div className="bento-loading">Reading port activity…</div>}><WorldPreview /></Suspense></MotionCard>
            <MotionCard className="bento-memory"><div id="memory" className="scroll-mt-8"><MemoryCards /></div></MotionCard>
            <MotionCard className="bento-connections"><ConnectedDiagram /></MotionCard>
            <MotionCard className="bento-crew"><AgentRelay /></MotionCard>
          </div>
        </section>
        <section className="landing-proof landing-section"><div><p className="hero-kicker">No black boxes at the desk</p><h2 className="display">Show the work.<br /><em className="landing-mark">Keep the context.</em></h2><p className="proof-description">Every episode keeps observations, actions and outcomes connected. Revisit the evidence, see what an agent found, and learn from how the story ended.</p><ul className="proof-points">{["Versioned facts, with the history intact", "Reasoning through graph tools over MCP", "Persistent sessions, separated by tenant"].map((text) => <li key={text}><ShieldCheck size={15} aria-hidden />{text}</li>)}</ul><Link href={docs("/showcase")} className="hero-secondary">Explore the use cases<ArrowUpRight size={14} aria-hidden /></Link></div><Suspense fallback={<div className="card h-96" />}><EpisodePreview /></Suspense></section>
        <section className="landing-final-cta"><span className="cta-orbit cta-orbit-one" aria-hidden /><span className="cta-orbit cta-orbit-two" aria-hidden /><div><p className="hero-kicker">Make your next move connected</p><h2 className="display">A world of signals.<br /><em>One lighthouse.</em></h2><p>Bring the evidence together. Give your agents somewhere to remember.</p></div><div><Link href="/dashboard" className="button">Open the workspace<ArrowRight size={16} aria-hidden /></Link><Link href={docs("/library")} className="hero-secondary">Build with Lighthouse<ArrowUpRight size={14} aria-hidden /></Link></div></section>
      </main>
      <footer className="landing-footer"><div className="landing-footer-row"><Link href="/" className="landing-brand"><Logo size={27} /><span>Lighthouse<span>.</span></span></Link><p>Connected by memory.<br />Built on FalkorDB.</p><nav aria-label="Footer navigation"><Link href="/sources">Data & provenance</Link><Link href={docs()}>Documentation ↗</Link><Link href="/agents">The crew ↗</Link></nav></div><div className="landing-footer-bottom"><span>Fintraffic / digitraffic.fi · CC BY 4.0 &nbsp; / &nbsp; Source: IMF PortWatch</span><span>See clearly. Act with context.</span></div></footer>
    </div>
  </div>;
}

async function Snapshot() {
  const [world, status, berths] = await Promise.all([maybe<World>("/api/world"), maybe<Status>("/api/status"), maybe<Berth[]>("/api/berths")]);
  return <section className="landing-snapshot" aria-label="Current graph snapshot"><div className="snapshot-heading"><span className="snapshot-dot" /><span>Inside the graph<span className="snapshot-date">Global observations: <When at={world?.newest_day} day /></span></span></div>{[["Mapped ports", world?.ports.length], ["Open episodes", status?.open_episodes], ["Berths monitored", berths?.length], ["Lessons retained", status?.counts.Lesson]].map(([label, value]) => <div className="snapshot-metric" key={String(label)}><strong>{number(value)}</strong><span>{label}</span></div>)}</section>;
}

async function WorldPreview() {
  const world = await maybe<World>("/api/world");
  return <><header className="bento-heading"><span className="feature-index">01 / WATCH</span><Globe2 size={19} aria-hidden /></header><div className="world-bento-title"><h3 className="display">The whole world.<br />The changes that matter.</h3><span className="bento-source-label">Real graph data<br /><When at={world?.newest_day} day /></span></div><p className="bento-description">Daily port activity, connected to the places behind it.</p><div className="bento-world-map">{world ? <WorldMap world={world} /> : <div className="bento-loading">Port activity is temporarily unavailable.</div>}</div><div className="world-bento-footer"><span><Radar size={13} aria-hidden />{world ? `${Object.keys(world.unusual).length} unusual ports on the latest source day` : "Source dates stay attached to evidence"}</span><Link href="/ports" className="bento-link">Explore ports<ArrowUpRight size={14} aria-hidden /></Link></div></>;
}

async function EpisodePreview() {
  const episodes = await maybe<EpisodeSummary[]>("/api/episodes", { limit: 20 });
  const shown = episodes?.find((episode) => episode.entry_count > 1) ?? episodes?.[0];
  const episode = shown ? await maybe<Episode>(`/api/episodes/${segments(shown.id)}`) : null;
  return <div className="card !p-6 md:!p-8"><header className="flex items-center justify-between gap-4"><p className="flex items-center gap-2 text-xs font-medium"><GitBranch size={16} className="text-[var(--beam)]" aria-hidden />An episode from the graph</p><Badge tone={episode?.closed_at ? "closed" : "observation"}>{episode ? episode.closed_at ? "Completed" : "Open" : "Awaiting data"}</Badge></header>
    {episode ? <><ol className="mt-7 grid gap-6 border-l pl-5 landing-rule">{episode.entries.slice(0, 4).map((entry, index) => <li key={entry.id} className="relative"><span className="absolute top-1 -left-[24px] h-1.5 w-1.5 rounded-full bg-[var(--beam)]" /><p className="feature-index mb-2">{String(index + 1).padStart(2, "0")} / {agentName(entry.by).toUpperCase()} / {entry.type.toUpperCase()}</p><p className="text-sm leading-relaxed">{said(entry)}</p><p className="mt-2 text-[10px] text-faint"><When at={entry.at} /> · {entry.cites.length} evidence references</p></li>)}</ol><Link href={`/episodes/${segments(episode.id)}`} className="mt-7 flex items-center justify-between border-t pt-5 text-xs text-[var(--beam)] landing-rule">Follow the complete episode<ArrowRight size={14} aria-hidden /></Link></> : <p className="py-10 text-sm leading-relaxed text-muted">The first episode appears when a Watcher finds unusual port activity or an expected berth overload. Each observation and action will appear here with its evidence.</p>}
    <div className="mt-5 flex items-center gap-2 text-[10px] text-faint"><Database size={12} aria-hidden />Read from the running graph. No sample incidents.</div>
  </div>;
}
