import Link from "next/link";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  History,
  LockKeyhole,
  Network,
  Waypoints,
} from "lucide-react";
import { Brand, Mark } from "./components/Brand";
import { MemoryWalkthrough } from "./components/MemoryWalkthrough";
import { CodeExample, MemoryFlow } from "./components/MemoryFlow";
const DOCS = process.env.NEXT_PUBLIC_MEMORY_DOCS_URL ?? "http://localhost:3002";
const FEATURES = [
  {
    icon: History,
    n: "01",
    title: "Facts change.\nContext shouldn't disappear.",
    text: "Versioned entities and relationships preserve what was true, when it was true, and what came before.",
    tag: "TEMPORAL MEMORY",
    href: "/history",
  },
  {
    icon: Network,
    n: "02",
    title: "A connection is more useful\nwhen you can follow it.",
    text: "Traverse the graph, recall shared evidence, and explain a connection step by step. Add text or vector retrieval when your task needs it.",
    tag: "CONNECTED RECALL",
    href: "/recall",
  },
  {
    icon: Waypoints,
    n: "03",
    title: "Different agents.\nThe same understanding.",
    text: "Atomic task claims, leases, and evidence-linked handoffs keep work moving without copying context between agents.",
    tag: "SHARED STATE",
    href: "/coordination",
  },
];
export default function Home() {
  return (
    <div className="marketing">
      <header className="site-header">
        <Brand />
        <nav className="desktop-links" aria-label="Main navigation">
          <a href="#product">Why Lighthouse</a>
          <a href="#how-it-works">Developers</a>
          <a href="#use-cases">Use cases</a>
          <a href={DOCS}>
            Docs <ArrowUpRight size={13} />
          </a>
        </nav>
        <div className="header-actions">
          <Link href="/login" className="header-login">
            Sign in
          </Link>
          <Link href="/signup" className="button button-small">
            Start building <ArrowUpRight size={14} />
          </Link>
          <details className="mobile-menu">
            <summary aria-label="Open navigation">
              <span />
              <span />
            </summary>
            <nav aria-label="Mobile navigation">
              <a href="#product">Why Lighthouse</a>
              <a href="#how-it-works">Developers</a>
              <a href="#use-cases">Use cases</a>
              <a href={DOCS}>Documentation</a>
              <Link href="/login">Sign in</Link>
            </nav>
          </details>
        </div>
      </header>
      <main id="main" className="marketing-main">
        <section className="hero">
          <div className="hero-copy">
            <a className="announcement" href={`${DOCS}/model`}>
              <span>LIGHTHOUSE MEMORY / CONNECTED CONTEXT</span>
              <ArrowUpRight size={12} />
            </a>
            <h1>
              Every agent needs
              <br />a <em>memory.</em>
            </h1>
            <p className="hero-tagline">
              <ArrowRight size={23} />
              Make it connected.
            </p>
            <p>
              Turn scattered facts into context your agents can act on. Keep
              every version, follow the evidence, and carry the work forward.
            </p>
            <div className="hero-actions">
              <Link href="/signup" className="button">
                Start building
                <ArrowUpRight size={15} />
              </Link>
              <a href={`${DOCS}/library`} className="button button-outline">
                Explore the library
                <ArrowRight size={15} />
              </a>
            </div>
          </div>
          <MemoryFlow />
          <div className="hero-proof">
            <div>
              <History size={20} />
              <span>
                <strong>History stays intact.</strong>
                <small>Every change has a before.</small>
              </span>
            </div>
            <div>
              <Network size={20} />
              <span>
                <strong>Evidence stays connected.</strong>
                <small>Follow the path behind an answer.</small>
              </span>
            </div>
            <div>
              <LockKeyhole size={20} />
              <span>
                <strong>Access stays in your hands.</strong>
                <small>Private projects. Scoped keys.</small>
              </span>
            </div>
          </div>
        </section>
        <div className="compatibility">
          <span>
            YOUR MODELS. YOUR AGENTS.
            <br />
            <strong>ONE CONTINUOUS MEMORY.</strong>
          </span>
          <div>
            {["OpenAI", "Claude", "Gemini", "Ollama", "Your own model"].map(
              (name) => (
                <span key={name}>{name}</span>
              ),
            )}
          </div>
          <a href={`${DOCS}/integrations`}>
            How it connects
            <ArrowUpRight size={12} />
          </a>
        </div>
        <section id="product" className="section product-section">
          <div className="section-heading split-heading">
            <span className="eyebrow">01 / BUILT FOR CONTINUITY</span>
            <h2>
              Intelligence needs
              <br />
              <span>something to remember.</span>
            </h2>
            <p>
              A useful memory is more than a saved message. It connects what
              changed, why it mattered, and what happened next.
            </p>
          </div>
          <div className="feature-grid">
            {FEATURES.map(({ icon: Icon, n, title, text, tag, href }) => (
              <article className="feature-card" key={n}>
                <div className="feature-top">
                  <Icon size={21} />
                  <span>{n}</span>
                </div>
                <small>{tag}</small>
                <h3>{title}</h3>
                <p>{text}</p>
                {n === "01" ? (
                  <div
                    className="history-preview"
                    aria-label="Illustrated version history"
                  >
                    <span>release / deployment-42</span>
                    <div>
                      <i />
                      <strong>Observed</strong>
                      <code>09:14</code>
                    </div>
                    <div>
                      <i />
                      <strong>Investigated</strong>
                      <code>09:26</code>
                    </div>
                    <div>
                      <i />
                      <strong>Resolved</strong>
                      <code>10:03</code>
                    </div>
                    <small>Three states. One continuous record.</small>
                  </div>
                ) : null}
                <a href={DOCS + href}>
                  Explore the capability
                  <ArrowUpRight size={13} />
                </a>
              </article>
            ))}
          </div>
        </section>
        <section id="how-it-works" className="section engine-section">
          <div className="engine-copy">
            <span className="eyebrow">02 / UNDER THE SURFACE</span>
            <h2>
              Write once.
              <br />
              Keep the whole story.
            </h2>
            <p>
              Structured observations become versioned graph memory. Your model
              decides how to reason; Lighthouse keeps the evidence connected.
            </p>
            <ol>
              {[
                ["Remember", "Ingest facts with a receipt for every write."],
                ["Retrieve", "Find context through relationships and history."],
                ["Coordinate", "Record decisions, claim work, and hand it on."],
              ].map(([title, text], i) => (
                <li key={title}>
                  <span>0{i + 1}</span>
                  <div>
                    <strong>{title}</strong>
                    <p>{text}</p>
                  </div>
                </li>
              ))}
            </ol>
            <a href={`${DOCS}/model`} className="text-link">
              Understand the memory model
              <ArrowRight size={15} />
            </a>
          </div>
          <CodeExample />
        </section>
        <MemoryWalkthrough docs={DOCS} />
        <section id="use-cases" className="section use-cases">
          <div>
            <span className="eyebrow">04 / BUILD SOMETHING THAT REMEMBERS</span>
            <h2>
              Your domain.
              <br />
              Your decisions.
              <br />
              <span>Connected context.</span>
            </h2>
          </div>
          <div className="use-case-list">
            {[
              [
                "Security agents",
                "Trace findings to affected services and earlier decisions.",
              ],
              [
                "Investigation agents",
                "Follow connected evidence and preserve the reasoning trail.",
              ],
              [
                "Codebase agents",
                "Track changes, dependencies, and the context behind a fix.",
              ],
              [
                "Personal assistants",
                "Recall relevant conversations within an authenticated user boundary.",
              ],
            ].map(([title, text], i) => (
              <a href={`${DOCS}/showcase`} key={title}>
                <span>0{i + 1}</span>
                <div>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </div>
                <ArrowUpRight size={17} />
              </a>
            ))}
          </div>
        </section>
        <section className="section trust-section">
          <LockKeyhole size={25} />
          <h2>
            Shared memory.
            <br />
            Clear boundaries.
          </h2>
          <p>
            Separate project graphs. Scoped, expiring API keys. Private user
            accounts. Your agents get the access you choose.
          </p>
          <a href={`${DOCS}/security`}>
            Understand the boundaries
            <ArrowUpRight size={14} />
          </a>
          <div className="trust-tags">
            <span>Project isolation</span>
            <span>Key revocation</span>
            <span>Versioned evidence</span>
          </div>
        </section>
        <section id="start" className="section pricing-section">
          <div className="section-heading">
            <span className="eyebrow">05 / START WITH A REAL PROJECT</span>
            <h2>
              Your next agent.
              <br />
              <span>A longer memory.</span>
            </h2>
            <p>
              Connect a project, preserve its context, and build on every
              observation.
            </p>
          </div>
          <div className="pricing-grid">
            <article className="price-card">
              <span className="plan-label">YOUR WORKSPACE</span>
              <h3>One place for connected context.</h3>
              <p>
                Create projects, issue scoped keys, and inspect the memory your
                agents share.
              </p>
              <ul>
                {[
                  "Projects with their own memory graph",
                  "Scoped API keys and usage history",
                  "Versioned facts and connections",
                  "A dashboard to inspect the evidence",
                ].map((text) => (
                  <li key={text}>
                    <Check size={14} />
                    {text}
                  </li>
                ))}
              </ul>
              <Link href="/signup" className="button">
                Create your workspace
                <ArrowUpRight size={14} />
              </Link>
            </article>
            <article className="price-card cloud-card">
              <span className="plan-label">BUILD YOUR WAY</span>
              <h3>
                Start with the API.
                <br />
                Go deeper with the library.
              </h3>
              <p>
                Write structured memories through the API. Use the Python
                library for episodes, lessons, and agent coordination.
              </p>
              <a href={`${DOCS}/memory-api`} className="button button-outline">
                Explore the API
                <ArrowUpRight size={14} />
              </a>
              <a href={`${DOCS}/library`} className="cloud-status">
                Open the Python quickstart →
              </a>
            </article>
          </div>
        </section>
        <section className="final-cta">
          <Mark size={48} />
          <p className="eyebrow">EVERY NEXT STEP HAS A BEFORE.</p>
          <h2>Give it a memory.</h2>
          <Link href="/signup" className="button">
            Start building with Lighthouse
            <ArrowUpRight size={15} />
          </Link>
          <a href={`${DOCS}/library`}>
            Or start with the Python library
            <ArrowRight size={13} />
          </a>
        </section>
        <footer className="marketing-footer">
          <Brand />
          <p>Connected memory for the agents you build.</p>
          <div>
            <a href={DOCS}>Documentation</a>
            <a href="https://github.com/MitudruDutta/lighthouse/tree/main/lighthouse-memory">
              Source code
              <ArrowUpRight size={12} />
            </a>
            <a href="#main" aria-label="Back to top">
              <ArrowDown size={15} style={{ transform: "rotate(180deg)" }} />
            </a>
          </div>
        </footer>
      </main>
    </div>
  );
}
