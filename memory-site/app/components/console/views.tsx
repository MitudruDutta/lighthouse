"use client";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  Database,
  Folder,
  GitBranch,
  History,
  KeyRound,
  Layers3,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";
import { CLIENTS } from "../../lib/agents";
import { call } from "../../lib/console";
import type { Fact, KeyRecord, Overview, Project, Summary } from "../../lib/types";
import { Code, Empty, LOCALE, MemoryGraph, OPERATIONS, Spark, day, moment } from "./ui";

export type State = {
  user: Overview["user"];
  project?: Project;
  projects: Project[];
  summary?: Summary;
  facts: Fact[];
  keys: KeyRecord[];
  loaded: boolean;
  clock: number;
  mcp: string;
  docs: string;
  href: (section: string, extra?: Record<string, string>) => string;
  go: (section: string) => void;
  refresh: () => void;
  notify: (message: string) => void;
  fail: (message: string) => void;
  newProject: () => void;
  newKey: (name?: string) => void;
  editFact: (fact: Fact | null) => void;
};

const active = (key: KeyRecord, clock: number) => !key.revoked && key.expires > clock;

function Stat({
  label,
  value,
  note,
  icon: Icon,
  children,
}: {
  label: string;
  value: number;
  note: string;
  icon: typeof Folder;
  children?: React.ReactNode;
}) {
  return (
    <article className="cx-stat">
      <header>
        <span>{label}</span>
        <Icon size={15} />
      </header>
      <strong>{value.toLocaleString(LOCALE)}</strong>
      <small>{note}</small>
      {children}
    </article>
  );
}

export function OverviewView({ s }: { s: State }) {
  const counts = s.summary?.counts ?? {};
  const calls = (s.summary?.days ?? []).reduce((sum, item) => sum + item.count, 0);
  const live = s.keys.filter((key) => active(key, s.clock)).length;
  const steps = [
    { done: s.projects.length > 0, title: "Create a project", text: "One graph per agent or app.", act: s.newProject },
    { done: s.keys.length > 0, title: "Create an API key", text: "Scoped to read, write, or both.", act: () => s.go("keys") },
    { done: s.facts.length > 0, title: "Write a first memory", text: "From the console, the API, or an agent.", act: () => s.editFact(null) },
    { done: calls > 0, title: "Connect an agent", text: "Claude Code over MCP, or the HTTP API.", act: () => s.go("agents") },
  ];
  const left = steps.filter((step) => !step.done).length;
  if (!s.project)
    return (
      <section className="cx-panel">
        <Empty
          title="Your memory starts with a project."
          text="A project is one graph with its own keys and usage. Create one for an agent, an app, or a team of agents."
          action={
            <button className="button button-small" onClick={s.newProject}>
              <Plus size={14} />
              New project
            </button>
          }
        />
      </section>
    );
  return (
    <>
      <div className="cx-stats">
        <Stat label="Memories" value={counts.Memory ?? 0} note="Current facts" icon={Database} />
        <Stat label="Versions kept" value={counts.State ?? 0} note="Every change, never overwritten" icon={History} />
        <Stat label="Episodes" value={counts.Episode ?? 0} note={`${counts.Task ?? 0} tasks`} icon={Layers3} />
        <Stat label="Requests, 14 days" value={calls} note={`${live} active key${live === 1 ? "" : "s"}`} icon={Activity}>
          <Spark days={s.summary?.days ?? []} />
        </Stat>
      </div>
      <div className="cx-actions">
        {[
          { title: "Add a memory", text: "A fact, with its links", icon: Plus, act: () => s.editFact(null) },
          { title: "Create an API key", text: "One per agent", icon: KeyRound, act: () => s.newKey() },
          { title: "Connect an agent", text: "Claude Code plugin", icon: Bot, act: () => s.go("agents") },
          { title: "Explore memory", text: "Search, links, versions", icon: Search, act: () => s.go("memory") },
        ].map(({ title, text, icon: Icon, act }) => (
          <button key={title} type="button" className="cx-action" onClick={act}>
            <span className="cx-symbol">
              <Icon size={17} />
            </span>
            <span>
              <strong>{title}</strong>
              <small>{text}</small>
            </span>
            <ArrowRight size={15} />
          </button>
        ))}
      </div>
      <div className="cx-columns">
        <section className="cx-panel">
          <header className="cx-panel-head">
            <div>
              <h2>Connected memory</h2>
              <p>The memories of {s.project.name} and the links between them.</p>
            </div>
            <Link href={s.href("memory")} className="cx-link">
              Open explorer <ArrowUpRight size={13} />
            </Link>
          </header>
          <MemoryGraph
            facts={s.facts}
            loading={!s.loaded}
            edges={s.summary?.edges ?? []}
            select={() => s.go("memory")}
          />
          <header className="cx-panel-head cx-subhead">
            <h2>Requests per day</h2>
            <span className="cx-muted">Last 14 days, UTC</span>
          </header>
          {s.summary?.days.length ? (
            <Bars days={s.summary.days} />
          ) : (
            <p className="cx-muted">Requests from agents and the console appear here.</p>
          )}
        </section>
        <div className="cx-stack">
          <section className="cx-panel cx-connect-card">
            <header className="cx-panel-head">
              <div>
                <h2>
                  <Bot size={16} /> Give an agent this memory
                </h2>
                <p>One command for Claude Code. Every other client is on Agents &amp; MCP.</p>
              </div>
            </header>
            <Code title="Claude Code" code={CLIENTS[0].code(s.mcp, "YOUR_PROJECT_API_KEY")} />
            <Link href={s.href("agents")} className="button button-small">
              Connect an agent
              <ArrowRight size={14} />
            </Link>
          </section>
          {left ? (
            <section className="cx-panel">
              <header className="cx-panel-head">
                <h2>Get started</h2>
                <span className="cx-muted">{steps.length - left} of {steps.length} done</span>
              </header>
              <ol className="cx-steps">
                {steps.map((step, index) => (
                  <li key={step.title} data-done={step.done || undefined}>
                    <button type="button" onClick={step.act}>
                      <span>{step.done ? <Check size={13} /> : index + 1}</span>
                      <span>
                        <strong>{step.title}</strong>
                        <small>{step.text}</small>
                      </span>
                      <ArrowRight size={14} />
                    </button>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}
          <section className="cx-panel">
            <header className="cx-panel-head">
              <h2>Recent activity</h2>
              <Link href={s.href("usage")} className="cx-link">
                Usage <ArrowUpRight size={13} />
              </Link>
            </header>
            {s.summary?.recent.length ? (
              <ul className="cx-activity">
                {s.summary.recent.slice(0, 5).map((event, index) => (
                  <li key={`${event.at}-${index}`}>
                    <Activity size={14} />
                    <span>{OPERATIONS[event.operation] ?? "Memory operation"}</span>
                    <time dateTime={new Date(event.at * 1000).toISOString()}>
                      {moment(event.at, s.user.timezone)}
                    </time>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="cx-muted">What your agents read and write appears here.</p>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

export function ProjectsView({ s }: { s: State }) {
  if (!s.projects.length)
    return (
      <section className="cx-panel">
        <Empty
          title="A clean slate for your agents."
          text="Each project has its own graph, API keys, and usage."
          action={
            <button className="button button-small" onClick={s.newProject}>
              <Plus size={14} />
              New project
            </button>
          }
        />
      </section>
    );
  return (
    <div className="cx-projects">
      {s.projects.map((item) => (
        <Link
          key={item.id}
          href={`/dashboard?project=${item.id}`}
          className="cx-project"
          aria-current={item.id === s.project?.id ? "true" : undefined}
        >
          <header>
            <span className="cx-symbol">
              <Folder size={18} />
            </span>
            <ArrowUpRight size={15} />
          </header>
          <h2>{item.name}</h2>
          <p>{item.description || "An independent graph for an agent’s memory."}</p>
          <footer>
            <code>{item.id.slice(0, 12)}</code>
            <span>Created {day(item.created, s.user.timezone)}</span>
          </footer>
        </Link>
      ))}
      <button type="button" className="cx-project cx-project-new" onClick={s.newProject}>
        <Plus size={20} />
        New project
      </button>
    </div>
  );
}

export function ExplorerView({ s }: { s: State }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Fact | null>(null);
  const [versions, setVersions] = useState<Record<string, unknown>[] | null>(null);
  const shown = s.facts.filter((fact) =>
    `${fact.title} ${fact.text} ${fact.key}`.toLowerCase().includes(query.toLowerCase()),
  );
  async function inspect(fact: Fact) {
    setSelected(fact);
    setVersions(null);
    try {
      setVersions(
        await call(`/projects/${s.project?.id}/memories/${encodeURIComponent(fact.key)}/history`),
      );
    } catch {
      setVersions([]);
      s.notify("History is temporarily unavailable.");
    }
  }
  return (
    <div className={selected ? "cx-explorer cx-explorer-open" : "cx-explorer"}>
      <section className="cx-panel">
        <header className="cx-panel-head">
          <div>
            <h2>Memories</h2>
            <p>{s.loaded ? `${s.facts.length} loaded, up to 100 shown` : "Loading…"}</p>
          </div>
          <button className="button button-small" disabled={!s.project} onClick={() => s.editFact(null)}>
            <Plus size={14} />
            Add memory
          </button>
        </header>
        <div className="cx-toolbar">
          <label>
            <Search size={15} />
            <input
              aria-label="Filter memories"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter by title, key, or text…"
            />
          </label>
          <span>
            <GitBranch size={14} />
            {s.summary?.edges.length ?? 0} links
          </span>
        </div>
        <MemoryGraph
          facts={shown}
          loading={!s.loaded}
          edges={s.summary?.edges ?? []}
          select={(fact) => void inspect(fact)}
        />
        {shown.length ? (
          <div className="cx-table" role="region" aria-label="Memories" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th>Memory</th>
                  <th>Text</th>
                  <th>Metadata</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {shown.map((fact) => (
                  <tr key={fact.key} data-selected={fact.key === selected?.key || undefined}>
                    <td>
                      <button className="cx-text-button" onClick={() => void inspect(fact)}>
                        <strong>{fact.title}</strong>
                        <small>{fact.key}</small>
                      </button>
                    </td>
                    <td className="cx-excerpt">
                      {fact.text.slice(0, 140)}
                      {fact.text.length > 140 ? "…" : ""}
                    </td>
                    <td>{Object.keys(fact.metadata).length} fields</td>
                    <td>
                      <button className="button button-outline button-small" onClick={() => s.editFact(fact)}>
                        New version
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
      {selected ? (
        <aside className="cx-panel cx-detail" aria-label="Memory details">
          <header className="cx-panel-head">
            <div>
              <span className="cx-eyebrow">{selected.key}</span>
              <h2>{selected.title}</h2>
            </div>
            <button className="cx-icon" aria-label="Close memory details" onClick={() => setSelected(null)}>
              <X size={17} />
            </button>
          </header>
          <p className="cx-fulltext">{selected.text}</p>
          {Object.keys(selected.metadata).length ? (
            <pre tabIndex={0}>{JSON.stringify(selected.metadata, null, 2)}</pre>
          ) : null}
          <h3>
            <History size={14} /> Versions
          </h3>
          {versions === null ? (
            <p className="cx-muted">Loading history…</p>
          ) : (
            <ol className="cx-versions">
              {[...versions].reverse().map((version, index) => (
                <li key={index} data-current={index === 0 || undefined}>
                  <strong>{String(version.title ?? selected.title)}</strong>
                  <p>{String(version.text ?? "")}</p>
                  <small>
                    {index === 0 ? "Current · " : ""}from {String(version.valid_from ?? "")} UTC
                  </small>
                </li>
              ))}
            </ol>
          )}
        </aside>
      ) : null}
    </div>
  );
}

export function KeysView({ s }: { s: State }) {
  async function revoke(key: KeyRecord) {
    if (!window.confirm(`Revoke “${key.name}”? Requests that use this key stop working.`)) return;
    try {
      await call(`/projects/${s.project?.id}/keys/${key.id}`, "DELETE");
      s.refresh();
      s.notify("API key revoked.");
    } catch (err) {
      s.fail((err as Error).message);
    }
  }
  return (
    <section className="cx-panel">
      <header className="cx-panel-head">
        <div>
          <h2>API keys of {s.project?.name ?? "this project"}</h2>
          <p>
            A key opens one project. Its name is the agent’s name in the memory: name each key after
            the agent that uses it.
          </p>
        </div>
        <button className="button button-small" disabled={!s.project} onClick={() => s.newKey()}>
          <Plus size={14} />
          Create API key
        </button>
      </header>
      {s.keys.length ? (
        <div className="cx-table" role="region" aria-label="API keys" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Key</th>
                <th>Access</th>
                <th>Last used</th>
                <th>Expires</th>
                <th>Status</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {s.keys.map((key) => (
                <tr key={key.id}>
                  <td>
                    <strong>{key.name}</strong>
                  </td>
                  <td>
                    <code>{key.prefix}…</code>
                  </td>
                  <td>
                    <div className="cx-scopes">
                      {key.scopes.map((scope) => (
                        <span key={scope}>{scope.replace("memory:", "")}</span>
                      ))}
                    </div>
                  </td>
                  <td>{day(key.last_used, s.user.timezone)}</td>
                  <td>{day(key.expires, s.user.timezone)}</td>
                  <td>
                    <span className="cx-pill" data-tone={active(key, s.clock) ? "good" : "off"}>
                      {key.revoked ? "Revoked" : key.expires < s.clock ? "Expired" : "Active"}
                    </span>
                  </td>
                  <td>
                    {!key.revoked ? (
                      <button className="cx-icon cx-danger" aria-label={`Revoke ${key.name}`} onClick={() => void revoke(key)}>
                        <Trash2 size={15} />
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          title="Give an agent a key to its memory."
          text={s.project ? "Create a key with only the access the agent needs." : "Create a project first."}
        />
      )}
      <p className="cx-note">
        <ShieldCheck size={15} />
        Keep keys on servers and in agent configs, never in browser code. Revoking takes effect on the
        next request.
      </p>
    </section>
  );
}

function Bars({ days }: { days: Summary["days"] }) {
  const most = Math.max(...days.map((item) => item.count), 1);
  return (
    <div className="cx-bars" role="img" aria-label="Requests per day over the last 14 days">
      {days.map((item) => (
        <div key={item.day} title={`${item.day}: ${item.count} requests`}>
          <span>{item.count}</span>
          <i style={{ height: `${Math.max(3, (item.count / most) * 100)}%` }} />
          <small>{item.day.slice(5)}</small>
        </div>
      ))}
    </div>
  );
}

export function UsageView({ s }: { s: State }) {
  const days = s.summary?.days ?? [];
  const total = (operation: string) =>
    s.summary?.usage.find((item) => item.operation === operation)?.count ?? 0;
  const groups: [string, string[]][] = [
    ["Writes", ["api.write", "console.write"]],
    ["Reads", ["api.read", "api.history", "api.connection"]],
    ["Episodes", ["api.episode", "api.episode.read", "api.entry"]],
    ["Tasks & handoffs", ["api.task", "api.handoff", "api.handoff.read"]],
  ];
  return (
    <>
      <div className="cx-stats">
        {groups.map(([label, operations]) => (
          <Stat
            key={label}
            label={label}
            value={operations.reduce((sum, operation) => sum + total(operation), 0)}
            note="All time"
            icon={Activity}
          />
        ))}
      </div>
      <section className="cx-panel">
        <header className="cx-panel-head">
          <h2>Requests per day</h2>
          <span className="cx-muted">Last 14 days, UTC</span>
        </header>
        {days.length ? (
          <Bars days={days} />
        ) : (
          <Empty title="No requests yet." text="API, MCP, and console operations appear here." />
        )}
      </section>
      <section className="cx-panel">
        <header className="cx-panel-head">
          <h2>Recent operations</h2>
        </header>
        {s.summary?.recent.length ? (
          <div className="cx-table" role="region" aria-label="Recent operations" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th>Operation</th>
                  <th>Result</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {s.summary.recent.map((item, index) => (
                  <tr key={index}>
                    <td>{OPERATIONS[item.operation] ?? item.operation}</td>
                    <td>
                      <span className="cx-pill" data-tone={item.status < 400 ? "good" : "off"}>
                        {item.status < 400 ? "Succeeded" : "Refused"}
                      </span>
                    </td>
                    <td>{moment(item.at, s.user.timezone)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="cx-muted">No operations yet.</p>
        )}
      </section>
    </>
  );
}

