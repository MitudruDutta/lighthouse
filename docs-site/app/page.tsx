import { ArrowRight, BookOpen, Code2, GitBranch, Layers3 } from "lucide-react";
import Link from "next/link";

const PATHS = [
  {
    icon: Code2,
    title: "Write your first memory",
    text: "Declare an entity, store its changes, and read what was true at any time.",
    href: "/library",
  },
  {
    icon: Layers3,
    title: "Understand the model",
    text: "Learn how entities, episodes, lessons, and playbooks connect.",
    href: "/model",
  },
  {
    icon: GitBranch,
    title: "Build connected agents",
    text: "Compose graph recall, task claims, and handoffs in your own agent.",
    href: "/integrations",
  },
  {
    icon: BookOpen,
    title: "Explore the Python API",
    text: "Find exact signatures and behaviour, generated from the library.",
    href: "/reference",
  },
];
export default function Home() {
  return (
    <>
      <div className="docs-home-hero">
        <span className="hero-kicker">
          LIGHTHOUSE MEMORY / DEVELOPER DOCUMENTATION
        </span>
        <h1>Memory your agents can follow.</h1>
        <p>
          Store structured facts, preserve their history, and connect
          observations to decisions. A model-independent memory library built on
          FalkorDB.
        </p>
        <Link href="/library" className="button-quiet">
          Start building{" "}
          <ArrowRight size={13} className="inline ml-2" aria-hidden />
        </Link>
      </div>
      <h2 id="choose-your-path">Choose your path</h2>
      <div className="docs-cards">
        {PATHS.map(({ icon: Icon, title, text, href }) => (
          <Link key={href} href={href} className="docs-card">
            <Icon size={21} strokeWidth={1.5} aria-hidden />
            <h3>{title}</h3>
            <p>{text}</p>
            <span>Read guide →</span>
          </Link>
        ))}
      </div>
      <h2 id="three-kinds-of-memory">Three kinds of memory. One graph.</h2>
      <p>
        <strong>Episodic memory</strong> records observations, actions, and
        outcomes in order. <strong>Semantic memory</strong> keeps lessons and
        the episodes supporting or contradicting them.{" "}
        <strong>Procedural memory</strong> stores versioned playbooks, their
        runs, and their outcomes.
      </p>
      <blockquote>
        <p>
          Structured writes need no LLM. Lighthouse Memory keeps facts by time
          and rule; your agent chooses how to reason about them.
        </p>
      </blockquote>
      <h2 id="what-the-library-provides">What the library provides</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Capability</th>
              <th>Use it for</th>
              <th>Guide</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Versioned entities and relations</td>
              <td>Explain what changed and reconstruct earlier context.</td>
              <td>
                <Link href="/history">History</Link>
              </td>
            </tr>
            <tr>
              <td>Graph, text, and vector recall</td>
              <td>Retrieve connected facts and relevant evidence.</td>
              <td>
                <Link href="/recall">Recall</Link>
              </td>
            </tr>
            <tr>
              <td>Atomic task claims and handoffs</td>
              <td>Coordinate workers through persistent shared state.</td>
              <td>
                <Link href="/coordination">Coordination</Link>
              </td>
            </tr>
            <tr>
              <td>Sessions and tenant graphs</td>
              <td>
                Keep conversation context within authenticated boundaries.
              </td>
              <td>
                <Link href="/tenants">Isolation</Link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <h2 id="why-falkordb">Why FalkorDB</h2>
      <p>
        Relationships remain queryable evidence. Native connected components and
        PageRank support graph-wide recall; shortest paths explain connections.
        Full-text and vector indexes provide complementary retrieval. Lighthouse
        adds time semantics, receipts, memory records, and coordination rules on
        top.
      </p>
      <Link href="/falkordb" className="link">
        Explore the FalkorDB capabilities →
      </Link>
      <h2 id="where-to-use-it">Where to use it</h2>
      <p>
        Compose these primitives for security triage, fraud investigation,
        codebase reasoning, or agents that remember across sessions. The library
        supplies memory; your application supplies policies, model calls, and
        actions.
      </p>
      <Link href="/showcase" className="link">
        Explore memory use cases →
      </Link>
    </>
  );
}
