"use client";
import GoogleButton from "./GoogleButton";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  Code2,
  Copy,
  Database,
  Folder,
  GitBranch,
  KeyRound,
  Layers3,
  LayoutDashboard,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { Brand } from "./Brand";
import type { Fact, KeyRecord, Overview, Project, Summary } from "../lib/types";
const NAV = [
  { id: "overview", name: "Overview", icon: LayoutDashboard },
  { id: "projects", name: "Projects", icon: Folder },
  { id: "memory", name: "Memory explorer", icon: Database },
  { id: "keys", name: "API keys", icon: KeyRound },
  { id: "usage", name: "Usage", icon: Activity },
  { id: "connect", name: "Connect your agents", icon: Code2 },
  { id: "settings", name: "Settings", icon: Settings },
];
async function call(path: string, method = "GET", body?: unknown) {
  const response = await fetch("/api/console" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail ?? "Please try again shortly.");
  return data;
}
function date(value: number | null) {
  return value
    ? new Date(value * 1000).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "Not used yet";
}
const ACTIVITY_NAMES: Record<string, string> = {
  "api.write": "Memory written through API",
  "api.read": "Memory retrieved",
  "api.history": "Version history inspected",
  "api.connection": "Evidence connection traced",
  "console.write": "Memory saved in console",
};
function activityTime(at: number, zone: string) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: zone,
    }).format(new Date(at * 1000));
  } catch {
    return (
      new Date(at * 1000).toISOString().slice(0, 16).replace("T", " ") + " UTC"
    );
  }
}
function CopyButton({
  value,
  label = "Copy",
}: {
  value: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="copy-button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch {
          setCopied(false);
        }
      }}
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}{" "}
      {copied ? "Copied" : label}
    </button>
  );
}
function Empty({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <span>
        <Database size={24} />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
function MemoryGraph({
  facts,
  edges,
  select,
}: {
  facts: Fact[];
  edges: Summary["edges"];
  select: (fact: Fact) => void;
}) {
  const nodes = facts.slice(0, 12);
  const height = nodes.length <= 3 ? 220 : 360;
  const point = (index: number) => {
    if (nodes.length === 1) return { x: 320, y: height / 2 };
    if (nodes.length === 2)
      return { x: index === 0 ? 180 : 460, y: height / 2 };
    const angle = (index / nodes.length) * Math.PI * 2 - Math.PI / 2;
    return {
      x: 320 + Math.cos(angle) * 210,
      y: height / 2 + Math.sin(angle) * (height / 2 - 45),
    };
  };
  return (
    <div className="project-graph">
      {nodes.length ? (
        <svg
          viewBox={`0 0 640 ${height}`}
          role="img"
          aria-label="Project memory relationships"
        >
          <defs>
            <pattern
              id="project-grid"
              width="20"
              height="20"
              patternUnits="userSpaceOnUse"
            >
              <circle cx="1" cy="1" r=".7" fill="#e0d3c2" />
            </pattern>
          </defs>
          <rect width="640" height={height} fill="url(#project-grid)" />
          {edges.map((edge, i) => {
            const a = nodes.findIndex((node) => node.key === edge.from),
              b = nodes.findIndex((node) => node.key === edge.to);
            if (a < 0 || b < 0) return null;
            return (
              <line
                key={i}
                x1={point(a).x}
                y1={point(a).y}
                x2={point(b).x}
                y2={point(b).y}
                stroke="#b87e57"
                strokeWidth="1.5"
              />
            );
          })}
          {nodes.map((fact, index) => {
            const p = point(index);
            return (
              <g
                key={fact.key}
                role="button"
                tabIndex={0}
                aria-label={`Inspect ${fact.title}`}
                onClick={() => select(fact)}
                onKeyDown={(event) => {
                  if (["Enter", " "].includes(event.key)) {
                    event.preventDefault();
                    select(fact);
                  }
                }}
              >
                <title>{`${fact.title} · ${fact.key}`}</title>
                <rect
                  x={p.x - 90}
                  y={p.y - 20}
                  width="180"
                  height="40"
                  rx="7"
                  fill="#fff"
                  stroke="#cbb19a"
                />
                <circle cx={p.x - 75} cy={p.y} r="3" fill="#b73f20" />
                <text x={p.x - 64} y={p.y + 4} fill="#4f382e" fontSize="12">
                  {fact.title.length > 24
                    ? fact.title.slice(0, 23) + "…"
                    : fact.title}
                </text>
              </g>
            );
          })}
        </svg>
      ) : (
        <Empty
          title="Your graph has room to grow."
          text="Add memories and link them to each other. Their connections will appear here."
        />
      )}
      <div className="graph-footer">
        <span>
          <i />
          Current relationships
        </span>
        <span>
          {nodes.length} of {facts.length} memories shown
        </span>
      </div>
    </div>
  );
}
export function Console({
  initial,
  view,
  requestedProject,
  docs,
  publicApi,
}: {
  initial: Overview;
  view: string;
  requestedProject?: string;
  docs: string;
  publicApi: string;
}) {
  const router = useRouter();
  const [clock] = useState(() => Date.now() / 1000);
  const [projects, setProjects] = useState<Project[]>(initial.projects);
  const [user, setUser] = useState(initial.user);
  const project =
    projects.find((item) => item.id === requestedProject) ?? projects[0];
  const pid = project?.id;
  const [revision, setRevision] = useState(0);
  const [snapshot, setSnapshot] = useState<{
    id: string;
    summary: Summary;
    facts: Fact[];
    keys: KeyRecord[];
  } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [menu, setMenu] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Fact | null>(null);
  const [versions, setVersions] = useState<Record<string, unknown>[]>([]);
  const [issued, setIssued] = useState<{ secret: string; name: string } | null>(
    null,
  );
  const [editing, setEditing] = useState<Fact | null>(null);
  const projectDialog = useRef<HTMLDialogElement>(null),
    keyDialog = useRef<HTMLDialogElement>(null),
    factDialog = useRef<HTMLDialogElement>(null),
    secretDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!pid) return;
    let stopped = false;
    Promise.all([
      call(`/projects/${pid}/summary`),
      call(`/projects/${pid}/memories`),
      call(`/projects/${pid}/keys`),
    ])
      .then(([summary, facts, keys]) => {
        if (!stopped) {
          setSnapshot({ id: pid, summary, facts, keys });
          setError("");
        }
      })
      .catch(() => {
        if (!stopped)
          setError(
            "We couldn't load this project just now. Please refresh and try again.",
          );
      });
    return () => {
      stopped = true;
    };
  }, [pid, revision]);
  const current = snapshot?.id === pid ? snapshot : null;
  const summary = current?.summary;
  const facts = current?.facts ?? [];
  const keys = current?.keys ?? [];
  const shown = facts.filter((fact) =>
    `${fact.title} ${fact.text} ${fact.key}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const href = (section: string, id = pid) =>
    `/dashboard${section === "overview" ? "" : "/" + section}${id ? "?project=" + id : ""}`;
  const refresh = () => setRevision((value) => value + 1);
  const openFact = (fact: Fact | null) => {
    setEditing(fact);
    setError("");
    factDialog.current?.showModal();
  };
  async function inspect(fact: Fact) {
    setSelected(fact);
    setVersions([]);
    try {
      setVersions(
        await call(
          `/projects/${pid}/memories/${encodeURIComponent(fact.key)}/history`,
        ),
      );
    } catch {
      setNotice("History is temporarily unavailable.");
    }
  }
  async function submit(
    event: React.FormEvent<HTMLFormElement>,
    action: (form: FormData) => Promise<void>,
  ) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await action(new FormData(event.currentTarget));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }
  const newProjectButton = (
    <button
      className="button button-small"
      onClick={() => projectDialog.current?.showModal()}
    >
      <Plus size={14} />
      New project
    </button>
  );
  return (
    <div className="console-shell">
      <aside className={`console-sidebar ${menu ? "menu-open" : ""}`}>
        <Brand />
        <div className="workspace-identity">
          <span className="workspace-avatar">
            {user.name[0]?.toUpperCase()}
          </span>
          <div>
            <strong>{initial.workspaces[0]?.name}</strong>
            <small>Personal workspace</small>
          </div>
          <ChevronDown size={13} />
        </div>
        <div className="nav-section-label">WORKSPACE</div>
        <nav aria-label="Console navigation">
          {NAV.map(({ id, name, icon: Icon }, index) => (
            <Link
              key={id}
              href={href(id)}
              aria-current={view === id ? "page" : undefined}
              className={index === 6 ? "nav-divider" : ""}
              onClick={() => setMenu(false)}
            >
              <Icon size={16} />
              {name}
              {id === "projects" ? <small>{projects.length}</small> : null}
            </Link>
          ))}
        </nav>
        <div className="console-sidebar-bottom">
          <a href={docs}>
            <BookOpen size={15} />
            Documentation
            <ArrowUpRight size={12} />
          </a>
          <Link href="/">
            Lighthouse Memory
            <ArrowUpRight size={12} />
          </Link>
          <div className="profile-mini">
            <span className="workspace-avatar">
              {user.name[0]?.toUpperCase()}
            </span>
            <div>
              <strong>{user.name}</strong>
              <small>{user.email}</small>
            </div>
            <button
              aria-label="Sign out"
              onClick={async () => {
                await fetch("/api/auth/logout", { method: "POST" });
                router.replace("/login");
                router.refresh();
              }}
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>
      <div className="console-main">
        <header className="console-topbar">
          <button
            className="mobile-menu icon-button"
            aria-label={menu ? "Close navigation" : "Open navigation"}
            onClick={() => setMenu(!menu)}
          >
            {menu ? <X size={18} /> : <Menu size={18} />}
          </button>
          <div className="console-breadcrumb">
            Workspace<span>/</span>
            {NAV.find((item) => item.id === view)?.name}
          </div>
          <div className="console-topbar-end">
            <a href={`${docs}/library`}>
              Quickstart
              <ArrowUpRight size={12} />
            </a>
          </div>
        </header>
        <main id="main" className="console-content">
          <div className="console-page-heading">
            <div>
              <span className="eyebrow">LIGHTHOUSE / MEMORY</span>
              <h1>
                {view === "overview"
                  ? `Good to see you, ${user.name.split(" ")[0]}.`
                  : NAV.find((item) => item.id === view)?.name}
              </h1>
              <p>
                {
                  (
                    {
                      overview: "A clear view of the context your agents keep.",
                      projects:
                        "Separate projects. Connected memories within each.",
                      keys: "Control who can read and write your project’s memory.",
                      memory:
                        "Explore facts, their connections, and what changed.",
                      usage:
                        "Actual operations recorded by the Memory API and console.",
                      connect:
                        "Give your agents access to this project’s memory.",
                      settings:
                        "Your profile and preferences, kept for your next visit.",
                    } as Record<string, string>
                  )[view]
                }
              </p>
            </div>
            <div className="page-actions">
              {projects.length > 0 &&
              !["projects", "settings"].includes(view) ? (
                <label className="project-select">
                  <Folder size={14} />
                  <select
                    aria-label="Active project"
                    value={pid}
                    onChange={(event) => {
                      setSelected(null);
                      router.push(href(view, event.target.value));
                    }}
                  >
                    {projects.map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <button
                className="icon-button"
                aria-label="Refresh project"
                onClick={refresh}
              >
                <RefreshCw size={16} />
              </button>
              {view === "projects" ? newProjectButton : null}
            </div>
          </div>
          {error ? (
            <div className="alert error" role="alert">
              {error}
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={14} />
              </button>
            </div>
          ) : null}
          {notice ? (
            <div className="alert" role="status">
              {notice}
              <button
                onClick={() => setNotice("")}
                aria-label="Dismiss notification"
              >
                <X size={14} />
              </button>
            </div>
          ) : null}
          {view === "overview" ? (
            <>
              <section className="welcome-panel">
                <div>
                  <span className="eyebrow">YOUR AGENTS’ NEXT CHAPTER</span>
                  <h2>
                    {projects.length
                      ? "Small facts. A bigger picture."
                      : "Your memory starts with a project."}
                  </h2>
                  <p>
                    {projects.length
                      ? "Write a memory, connect it to what came before, and follow the evidence."
                      : "Create a project, issue a scoped key, and start building context your agents can return to."}
                  </p>
                  {projects.length ? (
                    <Link href={href("memory")} className="button button-small">
                      Explore memory
                      <ArrowRight size={14} />
                    </Link>
                  ) : (
                    newProjectButton
                  )}
                </div>
                <div className="welcome-graphic" aria-hidden>
                  <Layers3 size={80} strokeWidth={0.7} />
                  <span>OBSERVE → REMEMBER → BUILD</span>
                </div>
              </section>
              <div className="console-stats">
                {[
                  ["Projects", projects.length, Folder],
                  ["Memories", summary?.counts.Memory ?? 0, Database],
                  ["Stored versions", summary?.counts.State ?? 0, Layers3],
                  [
                    "Active API keys",
                    keys.filter((key) => !key.revoked && key.expires > clock)
                      .length,
                    KeyRound,
                  ],
                ].map(([label, count, Icon]) => {
                  const Symbol = Icon as typeof Folder;
                  return (
                    <article className="stat-card" key={String(label)}>
                      <div>
                        <span>{String(label)}</span>
                        <Symbol size={16} />
                      </div>
                      <strong>{Number(count).toLocaleString()}</strong>
                      <small>
                        {label === "Projects"
                          ? "In your workspace"
                          : project
                            ? project.name
                            : "Create a project to begin"}
                      </small>
                    </article>
                  );
                })}
              </div>
              <div className="console-two-columns">
                <section className="panel">
                  <div className="panel-heading">
                    <h2>Connected memory</h2>
                    <Link href={href("memory")}>
                      Open explorer
                      <ArrowUpRight size={13} />
                    </Link>
                  </div>
                  <MemoryGraph
                    facts={facts}
                    edges={summary?.edges ?? []}
                    select={(fact) => {
                      router.push(href("memory"));
                      void inspect(fact);
                    }}
                  />
                  <div className="recent-memory-activity">
                    <div>
                      <h3>Recent activity</h3>
                      <Link href={href("usage")}>
                        View usage <ArrowUpRight size={13} />
                      </Link>
                    </div>
                    {summary?.recent.length ? (
                      <ul>
                        {summary.recent.slice(0, 4).map((event, index) => (
                          <li key={`${event.at}-${index}`}>
                            <span className="activity-symbol">
                              <Activity size={15} />
                            </span>
                            <strong>
                              {ACTIVITY_NAMES[event.operation] ??
                                "Memory operation completed"}
                            </strong>
                            <time
                              dateTime={new Date(event.at * 1000).toISOString()}
                            >
                              {activityTime(event.at, user.timezone)}
                            </time>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>Successful memory operations will appear here.</p>
                    )}
                  </div>
                </section>
                <section className="panel">
                  <div className="panel-heading">
                    <h2>Getting started</h2>
                    <span className="muted">
                      {projects.length && keys.length && facts.length
                        ? "Setup complete"
                        : "Your first workflow"}
                    </span>
                  </div>
                  <ol className="onboarding-list">
                    {[
                      {
                        done: projects.length > 0,
                        title: "Create a project",
                        text: "Give an agent or workflow its own memory.",
                        action: "project",
                      },
                      {
                        done: keys.length > 0,
                        title: "Create an API key",
                        text: "Choose read and write access for your agent.",
                        action: "keys",
                      },
                      {
                        done: facts.length > 0,
                        title: "Add your first memory",
                        text: "Use the console or connect through the API.",
                        action: "memory",
                      },
                    ].map((step, i) => (
                      <li key={step.title}>
                        <button
                          onClick={() => {
                            if (step.action === "keys")
                              router.push(href("keys"));
                            else if (step.action === "memory" && pid)
                              openFact(null);
                            else projectDialog.current?.showModal();
                          }}
                        >
                          <span className={step.done ? "step-done" : ""}>
                            {step.done ? <Check size={14} /> : i + 1}
                          </span>
                          <div>
                            <strong>{step.title}</strong>
                            <small>{step.text}</small>
                          </div>
                          <ArrowUpRight size={14} />
                        </button>
                      </li>
                    ))}
                  </ol>
                  <a className="panel-help" href={`${docs}/library`}>
                    <BookOpen size={16} />
                    <div>
                      <strong>Start with the fundamentals.</strong>
                      <span>Read the Memory quickstart.</span>
                    </div>
                    <ArrowUpRight size={14} />
                  </a>
                </section>
              </div>
            </>
          ) : null}
          {view === "projects" ? (
            <section className="panel">
              {projects.length ? (
                <div className="project-grid">
                  {projects.map((item) => (
                    <Link
                      key={item.id}
                      href={href("overview", item.id)}
                      className="project-card"
                    >
                      <div>
                        <span className="project-symbol">
                          <Folder size={20} />
                        </span>
                        <ArrowUpRight size={15} />
                      </div>
                      <h2>{item.name}</h2>
                      <p>
                        {item.description ||
                          "An independent graph for your agent’s memory."}
                      </p>
                      <footer>
                        <code>{item.id.slice(0, 12)}</code>
                        <span>Created {date(item.created)}</span>
                      </footer>
                    </Link>
                  ))}
                </div>
              ) : (
                <Empty
                  title="A clean slate for your agents."
                  text="Each project has its own graph, API keys, and usage history."
                  action={newProjectButton}
                />
              )}
            </section>
          ) : null}
          {view === "keys" ? (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Project API keys</h2>
                  <p>
                    Secrets appear once. Store them securely and keep them out
                    of browser code.
                  </p>
                </div>
                <button
                  className="button button-small"
                  disabled={!pid}
                  onClick={() => keyDialog.current?.showModal()}
                >
                  <Plus size={14} />
                  Create API key
                </button>
              </div>
              {keys.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Key prefix</th>
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
                      {keys.map((key) => (
                        <tr key={key.id}>
                          <td>
                            <strong>{key.name}</strong>
                          </td>
                          <td>
                            <code>{key.prefix}…</code>
                          </td>
                          <td>
                            <div className="scopes">
                              {key.scopes.map((scope) => (
                                <span key={scope}>
                                  {scope.replace("memory:", "")}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td>{date(key.last_used)}</td>
                          <td>{date(key.expires)}</td>
                          <td>
                            <span
                              className={`status-pill ${key.revoked ? "revoked" : ""}`}
                            >
                              {key.revoked
                                ? "Revoked"
                                : key.expires < clock
                                  ? "Expired"
                                  : "Active"}
                            </span>
                          </td>
                          <td>
                            {!key.revoked ? (
                              <button
                                className="icon-button danger"
                                aria-label={`Revoke ${key.name}`}
                                onClick={async () => {
                                  if (
                                    !window.confirm(
                                      `Revoke “${key.name}”? Requests using this key will stop working.`,
                                    )
                                  )
                                    return;
                                  try {
                                    await call(
                                      `/projects/${pid}/keys/${key.id}`,
                                      "DELETE",
                                    );
                                    refresh();
                                    setNotice("API key revoked.");
                                  } catch (err) {
                                    setError((err as Error).message);
                                  }
                                }}
                              >
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
                  text={
                    pid
                      ? "Create a key with only the access your integration needs."
                      : "Create a project first, then issue an API key."
                  }
                  action={!pid ? newProjectButton : undefined}
                />
              )}
              <div className="info-strip">
                <ShieldCheck size={17} />
                <p>
                  Each key belongs to one project. Revocation takes effect on
                  its next request.
                </p>
              </div>
            </section>
          ) : null}
          {view === "memory" ? (
            <>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Memory explorer</h2>
                    <p>{facts.length} memories loaded · up to 100 shown</p>
                  </div>
                  <button
                    className="button button-small"
                    disabled={!pid}
                    onClick={() => openFact(null)}
                  >
                    <Plus size={14} />
                    Add memory
                  </button>
                </div>
                <div className="explorer-toolbar">
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
                    {summary?.edges.length ?? 0} visible relationships
                  </span>
                </div>
                <MemoryGraph
                  facts={shown}
                  edges={summary?.edges ?? []}
                  select={(fact) => void inspect(fact)}
                />
                {facts.length ? (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Memory</th>
                          <th>Content</th>
                          <th>Metadata</th>
                          <th>
                            <span className="sr-only">Actions</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {shown.map((fact) => (
                          <tr key={fact.key}>
                            <td>
                              <button
                                className="text-button"
                                onClick={() => void inspect(fact)}
                              >
                                <strong>{fact.title}</strong>
                                <small>{fact.key}</small>
                              </button>
                            </td>
                            <td className="memory-excerpt">
                              {fact.text.slice(0, 150)}
                              {fact.text.length > 150 ? "…" : ""}
                            </td>
                            <td>{Object.keys(fact.metadata).length} fields</td>
                            <td>
                              <button
                                className="button button-outline button-small"
                                onClick={() => openFact(fact)}
                              >
                                Update
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : !pid ? (
                  <div className="panel-help">{newProjectButton}</div>
                ) : null}
              </section>
              {selected ? (
                <section className="panel memory-detail">
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">MEMORY / {selected.key}</span>
                      <h2>{selected.title}</h2>
                    </div>
                    <button
                      className="icon-button"
                      aria-label="Close memory details"
                      onClick={() => setSelected(null)}
                    >
                      <X size={17} />
                    </button>
                  </div>
                  <p className="memory-fulltext">{selected.text}</p>
                  <h3>Metadata</h3>
                  <pre>{JSON.stringify(selected.metadata, null, 2)}</pre>
                  <h3>Version history</h3>
                  <p className="muted">
                    Each update preserves the previous state.
                  </p>
                  <ol className="version-list">
                    {versions.map((version, i) => (
                      <li key={i}>
                        <span className="status-dot" />
                        <div>
                          <strong>
                            {String(version.title ?? selected.title)}
                          </strong>
                          <p>{String(version.text ?? "")}</p>
                          <small>{String(version.valid_from ?? "")} UTC</small>
                        </div>
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}
            </>
          ) : null}
          {view === "usage" ? (
            <>
              <div className="console-stats">
                {["api.write", "api.read", "api.history", "api.connection"].map(
                  (operation) => (
                    <article className="stat-card" key={operation}>
                      <div>
                        <span>
                          {operation
                            .replace("api.", "")
                            .replace("connection", "Graph connections")}
                        </span>
                        <Activity size={16} />
                      </div>
                      <strong>
                        {summary?.usage.find(
                          (item) => item.operation === operation,
                        )?.count ?? 0}
                      </strong>
                      <small>Recorded operations · all time</small>
                    </article>
                  ),
                )}
              </div>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Activity over time</h2>
                  <span className="muted">Last 14 days · UTC</span>
                </div>
                <div className="usage-chart">
                  {summary?.days.length ? (
                    summary.days.map((day) => (
                      <div
                        key={day.day}
                        title={`${day.day}: ${day.count} operations`}
                      >
                        <span>{day.count}</span>
                        <i
                          style={{
                            height: Math.max(
                              4,
                              (day.count /
                                Math.max(
                                  ...summary.days.map((item) => item.count),
                                )) *
                                130,
                            ),
                          }}
                        />
                        <small>{day.day.slice(5)}</small>
                      </div>
                    ))
                  ) : (
                    <Empty
                      title="No operations recorded yet."
                      text="API requests and console writes appear here after you use a project."
                    />
                  )}
                </div>
                <p className="chart-note">
                  Includes successful API operations and console writes. Counts
                  are recorded by this service; no synthetic activity is added.
                </p>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Recent operations</h2>
                </div>
                {summary?.recent.length ? (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Operation</th>
                          <th>Result</th>
                          <th>Recorded at</th>
                        </tr>
                      </thead>
                      <tbody>
                        {summary.recent.map((item, i) => (
                          <tr key={i}>
                            <td>
                              <code>{item.operation}</code>
                            </td>
                            <td>
                              <span className="status-pill">{item.status}</span>
                            </td>
                            <td>{new Date(item.at * 1000).toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="muted">No operations yet.</p>
                )}
              </section>
            </>
          ) : null}
          {view === "connect" ? (
            <section className="panel connect-panel">
              <span className="project-symbol">
                <Code2 size={22} />
              </span>
              <h2>A key. A request. A memory.</h2>
              <p>
                Use your project API key from your application server. The key
                selects the project; callers cannot request another project’s
                graph.
              </p>
              <div className="connect-steps">
                <span>1. Create a project</span>
                <ArrowRight size={13} />
                <Link href={href("keys")}>2. Generate an API key</Link>
                <ArrowRight size={13} />
                <span>3. Send your first memory</span>
              </div>
              <label className="endpoint-label">
                Your Memory API endpoint<code>{publicApi}/v1/memories</code>
                <CopyButton value={`${publicApi}/v1/memories`} />
              </label>
              <div className="console-code">
                <div>
                  <span>Write a memory · cURL</span>
                  <CopyButton
                    value={`curl '${publicApi}/v1/memories' -H 'Authorization: Bearer YOUR_PROJECT_API_KEY' -H 'Content-Type: application/json' -d '{"key":"first-memory","title":"First memory","text":"A fact worth remembering."}'`}
                  />
                </div>
                <pre>{`curl '${publicApi}/v1/memories' \\\n  -H 'Authorization: Bearer YOUR_PROJECT_API_KEY' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "key": "first-memory",\n    "title": "First memory",\n    "text": "A fact worth remembering."\n  }'`}</pre>
              </div>
              <div className="connect-guides">
                <a href={`${publicApi}/docs`}>
                  Memory service API reference
                  <ArrowUpRight size={14} />
                </a>
                <a href={`${docs}/library`}>
                  Python library quickstart
                  <ArrowUpRight size={14} />
                </a>
                <a href={`${docs}/security`}>
                  Understand access boundaries
                  <ArrowUpRight size={14} />
                </a>
              </div>
            </section>
          ) : null}
          {view === "settings" ? (
            <section className="panel settings-panel">
              <div className="panel-heading">
                <h2>Your profile</h2>
              </div>
              <form
                onSubmit={(event) =>
                  submit(event, async (form) => {
                    const result = await call(
                      "/profile",
                      "PATCH",
                      Object.fromEntries(form),
                    );
                    setUser(result);
                    setNotice("Profile preferences saved.");
                  })
                }
              >
                <label>
                  Name
                  <input
                    name="name"
                    defaultValue={user.name}
                    required
                    maxLength={80}
                  />
                </label>
                <label>
                  Email address
                  <input value={user.email} disabled readOnly />
                </label>
                <label>
                  Time zone
                  <input
                    name="timezone"
                    defaultValue={user.timezone}
                    required
                    list="timezones"
                  />
                  <datalist id="timezones">
                    {[
                      "UTC",
                      "Asia/Kolkata",
                      "America/New_York",
                      "America/Los_Angeles",
                      "Europe/London",
                      "Europe/Berlin",
                      "Asia/Singapore",
                    ].map((zone) => (
                      <option key={zone} value={zone} />
                    ))}
                  </datalist>
                  <small>Saved to your account for future sessions.</small>
                </label>
                <button className="button button-small" disabled={busy}>
                  Save preferences
                  <Check size={14} />
                </button>
              </form>
              {user.google_connected ? (
                <div className="google-connected">
                  <Check size={16} />
                  Google connected · {user.email}
                </div>
              ) : (
                <div className="settings-google">
                  <p>
                    Connect your matching Google account for faster sign-in.
                  </p>
                  <GoogleButton connect />
                </div>
              )}
              <div className="info-strip">
                <ShieldCheck size={17} />
                <p>
                  Your profile is private to your account. Project memory is
                  accessible through your account or that project’s API keys.
                </p>
              </div>
            </section>
          ) : null}
          {!current &&
          pid &&
          !error &&
          !["settings", "projects", "connect"].includes(view) ? (
            <p className="loading-note" role="status">
              Loading project memory…
            </p>
          ) : null}
          <footer className="console-footer">
            <span>Lighthouse Memory</span>
            <a href={`${docs}/security`}>
              Security & limits
              <ArrowUpRight size={12} />
            </a>
          </footer>
        </main>
      </div>
      <dialog ref={projectDialog} className="app-dialog">
        <div className="dialog-heading">
          <span className="project-symbol">
            <Folder size={20} />
          </span>
          <button
            className="icon-button"
            aria-label="Close new project"
            onClick={() => projectDialog.current?.close()}
          >
            <X size={18} />
          </button>
        </div>
        <h2>A new place for context.</h2>
        <p>
          Create an independent project for an agent, application, or workflow.
        </p>
        <form
          onSubmit={(event) =>
            submit(event, async (form) => {
              const result = await call("/projects", "POST", {
                ...Object.fromEntries(form),
                workspace_id: initial.workspaces[0]?.id,
              });
              setProjects((items) => [result, ...items]);
              projectDialog.current?.close();
              router.push(href("overview", result.id));
              setNotice("Project created. Your memory graph is ready.");
            })
          }
        >
          <label>
            Project name
            <input
              name="name"
              required
              maxLength={80}
              placeholder="e.g. Research assistant"
            />
          </label>
          <label>
            Description <small>Optional</small>
            <textarea
              name="description"
              maxLength={400}
              rows={3}
              placeholder="What should this project remember?"
            />
          </label>
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
          <button className="button" disabled={busy}>
            Create project
            <ArrowRight size={14} />
          </button>
        </form>
      </dialog>
      <dialog ref={keyDialog} className="app-dialog">
        <div className="dialog-heading">
          <span className="project-symbol">
            <KeyRound size={20} />
          </span>
          <button
            className="icon-button"
            aria-label="Close API key form"
            onClick={() => keyDialog.current?.close()}
          >
            <X size={18} />
          </button>
        </div>
        <h2>Create a project API key.</h2>
        <p>
          This key can access {project?.name}. Its secret will be shown only
          once.
        </p>
        <form
          onSubmit={(event) =>
            submit(event, async (form) => {
              const data = await call(`/projects/${pid}/keys`, "POST", {
                name: form.get("name"),
                days: Number(form.get("days")),
                scopes: String(form.get("access")).split(","),
              });
              setIssued(data);
              keyDialog.current?.close();
              secretDialog.current?.showModal();
              refresh();
            })
          }
        >
          <label>
            Key name
            <input
              name="name"
              required
              maxLength={80}
              placeholder="e.g. Production agent"
            />
          </label>
          <label>
            Access
            <select name="access">
              <option value="memory:read,memory:write">
                Read and write memory
              </option>
              <option value="memory:read">Read memory only</option>
              <option value="memory:write">Write memory only</option>
            </select>
          </label>
          <label>
            Expires in
            <select name="days" defaultValue="90">
              <option value="30">30 days</option>
              <option value="90">90 days</option>
              <option value="365">365 days</option>
            </select>
          </label>
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
          <button className="button" disabled={busy}>
            Generate API key
            <KeyRound size={14} />
          </button>
        </form>
      </dialog>
      <dialog
        ref={secretDialog}
        className="app-dialog secret-dialog"
        onClose={() => setIssued(null)}
      >
        <span className="project-symbol">
          <ShieldCheck size={22} />
        </span>
        <h2>Your key is ready.</h2>
        <p>
          Copy it now. After closing this window, the secret cannot be
          recovered.
        </p>
        {issued ? (
          <>
            <label>
              {issued.name}
              <code data-testid="new-key" className="secret-value">
                {issued.secret}
              </code>
            </label>
            <CopyButton value={issued.secret} label="Copy API key" />
          </>
        ) : null}
        <button
          className="button"
          onClick={() => {
            secretDialog.current?.close();
            setIssued(null);
          }}
        >
          I&apos;ve saved my key
          <Check size={14} />
        </button>
      </dialog>
      <dialog ref={factDialog} className="app-dialog memory-dialog">
        <div className="dialog-heading">
          <span className="project-symbol">
            <Database size={20} />
          </span>
          <button
            className="icon-button"
            aria-label="Close memory form"
            onClick={() => factDialog.current?.close()}
          >
            <X size={18} />
          </button>
        </div>
        <h2>
          {editing ? "Keep the next version." : "Something worth remembering."}
        </h2>
        <p>
          {editing
            ? "Update the fact. Its earlier state stays in the graph."
            : "Store a structured memory and optionally connect it to existing context."}
        </p>
        <form
          key={editing?.key ?? "new"}
          onSubmit={(event) =>
            submit(event, async (form) => {
              let metadata;
              try {
                metadata = JSON.parse(String(form.get("metadata") || "{}"));
              } catch {
                throw new Error("Metadata must be a valid JSON object.");
              }
              await call(`/projects/${pid}/memories`, "POST", {
                key: form.get("key"),
                title: form.get("title"),
                text: form.get("text"),
                metadata,
                links: String(form.get("links") || "")
                  .split(",")
                  .map((value) => value.trim())
                  .filter(Boolean),
              });
              factDialog.current?.close();
              setSelected(null);
              refresh();
              setNotice(
                editing
                  ? "Memory updated. Earlier versions are preserved."
                  : "Memory saved to this project.",
              );
            })
          }
        >
          <label>
            Identifier
            <input
              name="key"
              required
              maxLength={100}
              pattern="[A-Za-z0-9][A-Za-z0-9_.:/-]{0,99}"
              readOnly={!!editing}
              defaultValue={editing?.key ?? ""}
              placeholder="e.g. decision-001"
            />
          </label>
          <label>
            Title
            <input
              name="title"
              required
              maxLength={200}
              defaultValue={editing?.title ?? ""}
            />
          </label>
          <label>
            Memory
            <textarea
              name="text"
              rows={4}
              maxLength={12000}
              defaultValue={editing?.text ?? ""}
            />
          </label>
          <label>
            Metadata <small>JSON object</small>
            <textarea
              name="metadata"
              rows={2}
              defaultValue={JSON.stringify(editing?.metadata ?? {}, null, 2)}
            />
          </label>
          <label>
            Connect to existing memories{" "}
            <small>Comma-separated identifiers</small>
            <input
              name="links"
              defaultValue={
                editing
                  ? summary?.edges
                      .filter((edge) => edge.from === editing.key)
                      .map((edge) => edge.to)
                      .join(", ")
                  : ""
              }
              placeholder="e.g. incident-001, decision-002"
            />
          </label>
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
          <button className="button" disabled={busy}>
            {editing ? "Save new version" : "Save memory"}
            <ArrowRight size={14} />
          </button>
        </form>
      </dialog>
    </div>
  );
}
