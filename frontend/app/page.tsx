import {
  ArrowRight,
  ArrowUpRight,
  Database,
  GitBranch,
  Globe2,
  Radar,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { HarborScene } from "./components/HarborScene";
import {
  AgentRelay,
  ConnectedDiagram,
  MemoryCards,
  MemoryTape,
  MotionCard,
} from "./components/LandingMotion";
import { Logo } from "./components/Logo";
import { WorldMap } from "./components/WorldMap";
import { Badge, When, number } from "./components/ui";
import { agentName, said } from "./components/words";
import {
  type Berth,
  type Episode,
  type EpisodeSummary,
  type Status,
  type World,
  maybe,
  segments,
} from "./lib/api";
import { docs, MEMORY_URL } from "./lib/links";

export default function Landing() {
  return (
    <div className="night landing-v2">
      <a href="#product" className="skip-link">
        Skip to product
      </a>
      <div className="landing-shell">
        <header className="landing-nav">
          <Link href="/" className="landing-brand">
            <Logo size={33} />
            <span>
              Lighthouse<span>.</span>
            </span>
          </Link>
          <nav aria-label="Product navigation">
            <a href="#capabilities">The product</a>
            <a href={MEMORY_URL}>
              Lighthouse Memory <ArrowUpRight size={13} aria-hidden />
            </a>
            <Link href={docs()}>
              Memory docs <ArrowUpRight size={12} aria-hidden />
            </Link>
          </nav>
          <Link href="/dashboard" className="button-quiet landing-nav-cta">
            Open console
            <ArrowUpRight size={13} aria-hidden />
          </Link>
        </header>
        <main id="product">
          <section className="harbor-hero" aria-labelledby="landing-title">
            <div className="harbor-hero-copy">
              <a href={MEMORY_URL} className="hero-kicker hero-powered">
                <span />
                Powered by Lighthouse Memory
                <ArrowUpRight size={13} aria-hidden />
              </a>
              <h1 id="landing-title" className="display">
                See the signal.
                <br />
                Follow the <em>current.</em>
              </h1>
              <p className="hero-description">
                Your maritime operations console. Follow ports and vessels,
                investigate changes with evidence, and keep every decision
                connected.
              </p>
              <div className="hero-actions">
                <Link href="/dashboard" className="button">
                  Open console
                  <ArrowRight size={16} aria-hidden />
                </Link>
                <a href="#capabilities" className="hero-secondary">
                  See how it works
                  <ArrowRight size={15} aria-hidden />
                </a>
              </div>
              <div className="hero-foundation">
                <GitBranch size={15} aria-hidden />
                <span>Your ports. Your watchlist. Your next decision.</span>
                <a
                  className="falkor-tag"
                  href="https://www.falkordb.com/"
                  target="_blank"
                  rel="noreferrer"
                >
                  Built on FalkorDB ↗
                </a>
              </div>
            </div>
            <HarborScene />
          </section>
          <Suspense
            fallback={
              <div className="landing-snapshot snapshot-loading">
                Reading the connected world…
              </div>
            }
          >
            <Snapshot />
          </Suspense>
          <MemoryTape />
          <section id="capabilities" className="landing-section">
            <div className="landing-section-heading">
              <div>
                <p className="hero-kicker">Observe. Investigate. Decide.</p>
                <h2 className="display">
                  Intelligence.
                  <br />
                  <em className="landing-mark">With a memory.</em>
                </h2>
              </div>
              <p>
                A signal is just the beginning. Follow the evidence, give a case
                an owner, agree on a next step, and record the outcome.
              </p>
            </div>
            <div className="product-bento">
              <MotionCard className="bento-world">
                <Suspense
                  fallback={
                    <div className="bento-loading">Reading port activity…</div>
                  }
                >
                  <WorldPreview />
                </Suspense>
              </MotionCard>
              <MotionCard className="bento-memory">
                <div id="memory" className="scroll-mt-8">
                  <MemoryCards />
                </div>
              </MotionCard>
              <MotionCard className="bento-connections">
                <ConnectedDiagram />
              </MotionCard>
              <MotionCard className="bento-crew">
                <AgentRelay />
              </MotionCard>
            </div>
          </section>
          <section className="landing-proof landing-section">
            <div>
              <p className="hero-kicker">Every decision has a trail</p>
              <h2 className="display">
                Show the work.
                <br />
                <em className="landing-mark">Keep the context.</em>
              </h2>
              <p className="proof-description">
                Keep source observations, Desk assessments, and your decisions
                in view. Revisit why a case mattered, what you decided, and how
                it ended.
              </p>
              <ul className="proof-points">
                {[
                  "Evidence and source dates stay attached",
                  "The Desk investigates connected records",
                  "Your watchlist and decisions persist across sessions",
                ].map((text) => (
                  <li key={text}>
                    <ShieldCheck size={15} aria-hidden />
                    {text}
                  </li>
                ))}
              </ul>
              <Link href={docs("/showcase")} className="hero-secondary">
                How Lighthouse Memory works
                <ArrowUpRight size={14} aria-hidden />
              </Link>
            </div>
            <Suspense fallback={<div className="card h-96" />}>
              <EpisodePreview />
            </Suspense>
          </section>
          <section className="landing-final-cta">
            <span className="cta-orbit cta-orbit-one" aria-hidden />
            <span className="cta-orbit cta-orbit-two" aria-hidden />
            <div>
              <p className="hero-kicker">Turn context into your next move</p>
              <h2 className="display">
                Every signal deserves
                <br />
                <em>a next step.</em>
              </h2>
              <p>
                Follow your ports. Investigate with the Desk. Record what you
                decided and what happened next.
              </p>
            </div>
            <div>
              <Link href="/dashboard" className="button">
                Open console
                <ArrowRight size={16} aria-hidden />
              </Link>
              <a href={MEMORY_URL} className="hero-secondary">
                Meet Lighthouse Memory
                <ArrowUpRight size={14} aria-hidden />
              </a>
            </div>
          </section>
        </main>
        <footer className="landing-footer">
          <div className="landing-footer-row">
            <Link href="/" className="landing-brand">
              <Logo size={27} />
              <span>
                Lighthouse<span>.</span>
              </span>
            </Link>
            <p>
              Maritime intelligence.
              <br />
              <a href={MEMORY_URL}>Powered by Lighthouse Memory ↗</a>
            </p>
            <nav aria-label="Footer navigation">
              <Link href="/sources">Data & provenance</Link>
              <Link href={docs()}>Memory docs ↗</Link>
              <Link href="/agents">Agent activity ↗</Link>
            </nav>
          </div>
          <div className="landing-footer-bottom">
            <span>
              Fintraffic / digitraffic.fi · CC BY 4.0 &nbsp; / &nbsp; Source:
              IMF PortWatch
            </span>
            <span>See clearly. Act with context.</span>
          </div>
        </footer>
      </div>
    </div>
  );
}

async function Snapshot() {
  const [world, status, berths] = await Promise.all([
    maybe<World>("/api/world"),
    maybe<Status>("/api/status"),
    maybe<Berth[]>("/api/berths"),
  ]);
  return (
    <section className="landing-snapshot" aria-label="Current graph snapshot">
      <div className="snapshot-heading">
        <span className="snapshot-dot" />
        <span>
          Inside the graph
          <span className="snapshot-date">
            Global observations: <When at={world?.newest_day} day />
          </span>
        </span>
      </div>
      {[
        ["Mapped ports", world?.ports.length],
        ["Source signals", status?.open_episodes],
        ["Berths monitored", berths?.length],
        ["Lessons retained", status?.counts.Lesson],
      ].map(([label, value]) => (
        <div className="snapshot-metric" key={String(label)}>
          <strong>{number(value)}</strong>
          <span>{label}</span>
        </div>
      ))}
    </section>
  );
}

async function WorldPreview() {
  const world = await maybe<World>("/api/world");
  return (
    <>
      <header className="bento-heading">
        <span className="feature-index">01 / WATCH</span>
        <Globe2 size={19} aria-hidden />
      </header>
      <div className="world-bento-title">
        <h3 className="display">
          The whole world.
          <br />
          The changes that matter.
        </h3>
        <span className="bento-source-label">
          Real graph data
          <br />
          <When at={world?.newest_day} day />
        </span>
      </div>
      <p className="bento-description">
        Daily port activity, connected to the places behind it.
      </p>
      <div className="bento-world-map">
        {world ? (
          <WorldMap world={world} />
        ) : (
          <div className="bento-loading">
            Port activity is temporarily unavailable.
          </div>
        )}
      </div>
      <div className="world-bento-footer">
        <span>
          <Radar size={13} aria-hidden />
          {world
            ? `${Object.keys(world.unusual).length} unusual ports on the latest source day`
            : "Source dates stay attached to evidence"}
        </span>
        <Link href="/ports" className="bento-link">
          Explore ports
          <ArrowUpRight size={14} aria-hidden />
        </Link>
      </div>
    </>
  );
}

async function EpisodePreview() {
  const episodes = await maybe<EpisodeSummary[]>("/api/episodes", {
    limit: 20,
  });
  const shown =
    episodes?.find((episode) => episode.entry_count > 1) ?? episodes?.[0];
  const episode = shown
    ? await maybe<Episode>(`/api/episodes/${segments(shown.id)}`)
    : null;
  return (
    <div className="card !p-6 md:!p-8">
      <header className="flex items-center justify-between gap-4">
        <p className="flex items-center gap-2 text-xs font-medium">
          <GitBranch size={16} className="text-[var(--beam)]" aria-hidden />
          An episode from the graph
        </p>
        <Badge tone={episode?.closed_at ? "closed" : "observation"}>
          {episode
            ? episode.closed_at
              ? "Source cleared"
              : "Signal open"
            : "Awaiting data"}
        </Badge>
      </header>
      {episode ? (
        <>
          <ol className="landing-evidence-flow">
            {episode.entries.slice(0, 3).map((entry, index) => (
              <li key={entry.id}>
                <span className="feature-index">
                  {String(index + 1).padStart(2, "0")} /{" "}
                  {agentName(entry.by).toUpperCase()} /{" "}
                  {entry.type.toUpperCase()}
                </span>
                <p>{said(entry)}</p>
                <small>
                  <When at={entry.at} /> · {entry.cites.length} evidence
                  references
                </small>
              </li>
            ))}
          </ol>
          <Link
            href={`/episodes/${segments(episode.id)}`}
            className="mt-7 flex items-center justify-between border-t pt-5 text-xs text-[var(--beam)] landing-rule"
          >
            Follow the complete episode
            <ArrowRight size={14} aria-hidden />
          </Link>
        </>
      ) : (
        <p className="py-10 text-sm leading-relaxed text-muted">
          The first episode appears when a Watcher finds unusual port activity
          or an expected berth overload. Each observation and action will appear
          here with its evidence.
        </p>
      )}
      <div className="mt-5 flex items-center gap-2 text-[10px] text-faint">
        <Database size={12} aria-hidden />
        Observations stay linked to their source records.
      </div>
    </div>
  );
}
