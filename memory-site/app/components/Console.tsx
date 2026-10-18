"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  ChevronDown,
  Database,
  Folder,
  KeyRound,
  Menu,
  Plus,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import { call } from "../lib/console";
import type { Fact, KeyRecord, Overview, Project, Summary } from "../lib/types";
import { AgentsView } from "./console/Agents";
import { type Danger, PlanView, SettingsView } from "./console/Settings";
import { SECTIONS, Sidebar } from "./console/Sidebar";
import { CopyButton, useMenu } from "./console/ui";
import {
  ExplorerView,
  KeysView,
  OverviewView,
  ProjectsView,
  type State,
  UsageView,
} from "./console/views";

const TITLES: Record<string, [string, string]> = {
  overview: ["Overview", "What this project remembers, and who uses it."],
  memory: ["Memory explorer", "Facts, their links, and every version they had."],
  agents: ["Agents & MCP", "Connect Claude Code, Claude Desktop, or your own agent."],
  keys: ["API keys", "Who can read and write this project’s memory."],
  usage: ["Usage", "Operations recorded by the Memory API, MCP, and the console."],
  projects: ["Projects", "One graph each, with its own keys and usage."],
  plan: ["Plan & billing", "Your plan and how much of it you use."],
  settings: ["Settings", "Project, workspace, and profile."],
};
// Whether the sidebar is folded, kept by the browser. Storage that is off or full costs
// only the preference, not the toggle.
const FOLDED = "lighthouse-console-collapsed";
const watchers = new Set<() => void>();
let isFolded: boolean | undefined;
function folded() {
  if (isFolded === undefined) {
    try {
      isFolded = localStorage.getItem(FOLDED) === "1";
    } catch {
      isFolded = false;
    }
  }
  return isFolded;
}
function fold(value: boolean) {
  isFolded = value;
  try {
    localStorage.setItem(FOLDED, value ? "1" : "0");
  } catch {}
  watchers.forEach((watcher) => watcher());
}
function subscribe(watcher: () => void) {
  watchers.add(watcher);
  return () => void watchers.delete(watcher);
}

export function Console({
  initial,
  view,
  requestedProject,
  requestedWorkspace,
  tab,
  docs,
  publicApi,
}: {
  initial: Overview;
  view: string;
  requestedProject?: string;
  requestedWorkspace?: string;
  tab?: string;
  docs: string;
  publicApi: string;
}) {
  const router = useRouter();
  const [clock] = useState(() => Date.now() / 1000);
  const [user, setUser] = useState(initial.user);
  const [workspaces, setWorkspaces] = useState(initial.workspaces);
  const [allProjects, setProjects] = useState<Project[]>(initial.projects);
  const requested = allProjects.find((item) => item.id === requestedProject);
  const workspace =
    workspaces.find((item) => item.id === (requested?.workspace_id ?? requestedWorkspace)) ??
    workspaces[0];
  const projects = allProjects.filter((item) => item.workspace_id === workspace?.id);
  const project = requested ?? projects[0];
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
  const [open, setOpen] = useState(false);
  const collapsed = useSyncExternalStore(subscribe, folded, () => false);
  const [issued, setIssued] = useState<{ secret: string; name: string } | null>(null);
  // A key shown in the agent snippets belongs to the project it was made for.
  const [agentKey, setAgentKey] = useState<{ secret: string; name: string; project?: string } | null>(null);
  const [keyName, setKeyName] = useState("");
  const [editing, setEditing] = useState<Fact | null>(null);
  const [danger, setDanger] = useState<Danger | null>(null);
  const [typed, setTyped] = useState("");
  const [projectsOpen, setProjectsOpen, projectsRef] = useMenu();
  const projectDialog = useRef<HTMLDialogElement>(null);
  const workspaceDialog = useRef<HTMLDialogElement>(null);
  const keyDialog = useRef<HTMLDialogElement>(null);
  const secretDialog = useRef<HTMLDialogElement>(null);
  const factDialog = useRef<HTMLDialogElement>(null);
  const dangerDialog = useRef<HTMLDialogElement>(null);

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
        if (!stopped) setError("We couldn't load this project just now. Please refresh and try again.");
      });
    return () => {
      stopped = true;
    };
  }, [pid, revision]);

  const current = snapshot?.id === pid ? snapshot : null;
  const href = (section: string, extra: Record<string, string> = {}) => {
    const query = new URLSearchParams(
      pid ? { project: pid, ...extra } : { ...(workspace ? { workspace: workspace.id } : {}), ...extra },
    ).toString();
    return `/dashboard${section === "overview" ? "" : "/" + section}${query ? "?" + query : ""}`;
  };
  const refresh = () => setRevision((value) => value + 1);
  const toggle = () => fold(!collapsed);

  async function submit(event: React.FormEvent<HTMLFormElement>, action: (form: FormData) => Promise<void>) {
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

  const state: State = {
    user,
    project,
    projects,
    summary: current?.summary,
    facts: current?.facts ?? [],
    keys: current?.keys ?? [],
    loaded: !!current,
    clock,
    mcp: `${publicApi}/mcp`,
    docs,
    href,
    go: (section) => router.push(href(section)),
    refresh,
    notify: setNotice,
    fail: setError,
    newProject: () => projectDialog.current?.showModal(),
    newKey: (name = "") => {
      setKeyName(name);
      setError("");
      keyDialog.current?.showModal();
    },
    editFact: (fact) => {
      if (!pid) return;
      setEditing(fact);
      setError("");
      factDialog.current?.showModal();
    },
  };
  const [title, lead] = TITLES[view] ?? TITLES.overview;
  const projectScoped = SECTIONS[0].items.some(([id]) => id === view);

  return (
    <div className="cx-shell" data-collapsed={collapsed || undefined}>
      <Sidebar
        user={user}
        workspaces={workspaces}
        workspace={workspace}
        view={view}
        counts={{ projects: projects.length }}
        collapsed={collapsed}
        open={open}
        href={href}
        toggle={toggle}
        close={() => setOpen(false)}
        switchTo={(id) => router.push(`/dashboard?workspace=${id}`)}
        newWorkspace={() => workspaceDialog.current?.showModal()}
        signOut={async () => {
          await fetch("/api/auth/logout", { method: "POST" });
          router.replace("/login");
          router.refresh();
        }}
      />
      {open ? <button className="cx-scrim" aria-label="Close navigation" onClick={() => setOpen(false)} /> : null}
      <div className="cx-main">
        <header className="cx-topbar">
          <button
            className="cx-icon cx-menu-button"
            aria-label={open ? "Close navigation" : "Open navigation"}
            onClick={() => setOpen(!open)}
          >
            {open ? <X size={18} /> : <Menu size={18} />}
          </button>
          <nav className="cx-crumbs" aria-label="Location">
            <span className="cx-crumb-quiet">{workspace?.name}</span>
            <span aria-hidden>/</span>
            <div className="cx-project-switch" ref={projectsRef}>
              <button
                type="button"
                aria-haspopup="menu"
                aria-expanded={projectsOpen}
                onClick={() => setProjectsOpen(!projectsOpen)}
              >
                <Folder size={14} />
                {project?.name ?? "No project"}
                <ChevronDown size={13} />
              </button>
              {projectsOpen ? (
                <div className="cx-menu" role="menu" aria-label="Projects">
                  <p>Projects in {workspace?.name}</p>
                  {projects.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      role="menuitemradio"
                      aria-checked={item.id === pid}
                      onClick={() => {
                        setProjectsOpen(false);
                        router.push(`/dashboard${projectScoped && view !== "overview" ? "/" + view : ""}?project=${item.id}`);
                      }}
                    >
                      <Folder size={14} />
                      <span>{item.name}</span>
                      {item.id === pid ? <Check size={14} /> : null}
                    </button>
                  ))}
                  <hr />
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setProjectsOpen(false);
                      state.newProject();
                    }}
                  >
                    <Plus size={14} />
                    New project
                  </button>
                </div>
              ) : null}
            </div>
          </nav>
          <div className="cx-topbar-end">
            <span className="cx-plan-pill">Developer · free preview</span>
            <a href={docs} className="cx-link cx-hide-small">
              Docs <ArrowUpRight size={12} />
            </a>
            <button className="cx-icon" aria-label="Refresh" title="Refresh" onClick={refresh}>
              <RefreshCw size={16} />
            </button>
            <button className="button button-small" onClick={() => state.go("agents")}>
              <Bot size={14} />
              <span className="cx-hide-small">Connect agent</span>
            </button>
          </div>
        </header>
        <main id="main" className="cx-content">
          <div className="cx-heading">
            <div>
              <h1>{view === "overview" && project ? project.name : title}</h1>
              <p>{view === "overview" && project?.description ? project.description : lead}</p>
            </div>
            {view === "projects" && projects.length ? (
              <button className="button button-small" onClick={state.newProject}>
                <Plus size={14} />
                New project
              </button>
            ) : null}
          </div>
          {error ? (
            <div className="cx-alert" data-tone="error" role="alert">
              {error}
              <button onClick={() => setError("")} aria-label="Dismiss">
                <X size={14} />
              </button>
            </div>
          ) : null}
          {notice ? (
            <div className="cx-alert" role="status">
              {notice}
              <button onClick={() => setNotice("")} aria-label="Dismiss">
                <X size={14} />
              </button>
            </div>
          ) : null}
          {projectScoped && !project && view !== "overview" ? (
            <OverviewView s={state} />
          ) : view === "overview" ? (
            <OverviewView s={state} />
          ) : view === "projects" ? (
            <ProjectsView s={state} />
          ) : view === "memory" ? (
            <ExplorerView s={state} key={pid} />
          ) : view === "agents" ? (
            <AgentsView s={state} api={publicApi} secret={agentKey?.project === pid ? agentKey : null} />
          ) : view === "keys" ? (
            <KeysView s={state} />
          ) : view === "usage" ? (
            <UsageView s={state} />
          ) : view === "plan" ? (
            <PlanView s={state} workspaces={workspaces} docs={docs} />
          ) : (
            <SettingsView
              s={state}
              tab={tab ?? ""}
              key={`${workspace?.id}-${pid}`}
              workspace={workspace}
              workspaces={workspaces}
              setUser={setUser}
              renamed={(kind, value) =>
                kind === "project"
                  ? setProjects((items) => items.map((item) => (item.id === value.id ? { ...item, ...value } : item)))
                  : setWorkspaces((items) => items.map((item) => (item.id === value.id ? { ...item, name: value.name } : item)))
              }
              danger={(next) => {
                setTyped("");
                setDanger(next);
                dangerDialog.current?.showModal();
              }}
              deleteProject={async () => {
                await call(`/projects/${pid}`, "DELETE", { confirm: project?.name });
                const left = projects.filter((item) => item.id !== pid);
                setProjects((items) => items.filter((item) => item.id !== pid));
                router.push(left[0] ? `/dashboard/projects?project=${left[0].id}` : `/dashboard/projects?workspace=${workspace?.id}`);
                setNotice("Project deleted with its graph, keys, and usage.");
              }}
              deleteWorkspace={async () => {
                await call(`/workspaces/${workspace?.id}`, "DELETE", { confirm: workspace?.name });
                const left = workspaces.filter((item) => item.id !== workspace?.id);
                setWorkspaces(left);
                setProjects((items) => items.filter((item) => item.workspace_id !== workspace?.id));
                router.push(`/dashboard?workspace=${left[0]?.id}`);
                setNotice("Workspace deleted with its projects.");
              }}
            />
          )}
        </main>
      </div>

      <dialog ref={projectDialog} className="app-dialog">
        <div className="dialog-heading">
          <span className="cx-symbol">
            <Folder size={18} />
          </span>
          <button className="cx-icon" aria-label="Close" onClick={() => projectDialog.current?.close()}>
            <X size={18} />
          </button>
        </div>
        <h2>A new place for context.</h2>
        <p>A project is one graph, with its own keys and usage, in {workspace?.name}.</p>
        <form
          onSubmit={(event) =>
            submit(event, async (form) => {
              const result = await call("/projects", "POST", {
                ...Object.fromEntries(form),
                workspace_id: workspace?.id,
              });
              setProjects((items) => [result, ...items]);
              projectDialog.current?.close();
              router.push(`/dashboard?project=${result.id}`);
              setNotice("Project created. Its graph is ready.");
            })
          }
        >
          <label>
            Project name
            <input name="name" required maxLength={80} placeholder="e.g. Support agent" />
          </label>
          <label>
            Description <small>Optional</small>
            <textarea name="description" maxLength={400} rows={3} placeholder="What should this project remember?" />
          </label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="button" disabled={busy}>
            Create project
            <ArrowRight size={14} />
          </button>
        </form>
      </dialog>

      <dialog ref={workspaceDialog} className="app-dialog">
        <div className="dialog-heading">
          <span className="cx-symbol">
            <Database size={18} />
          </span>
          <button className="cx-icon" aria-label="Close" onClick={() => workspaceDialog.current?.close()}>
            <X size={18} />
          </button>
        </div>
        <h2>A new workspace.</h2>
        <p>Keep the projects of a client, a team, or an experiment apart.</p>
        <form
          onSubmit={(event) =>
            submit(event, async (form) => {
              const result = await call("/workspaces", "POST", { name: form.get("name") });
              setWorkspaces((items) => [...items, result]);
              workspaceDialog.current?.close();
              router.push(`/dashboard?workspace=${result.id}`);
              setNotice("Workspace created.");
            })
          }
        >
          <label>
            Workspace name
            <input name="name" required maxLength={80} placeholder="e.g. Client work" />
          </label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="button" disabled={busy}>
            Create workspace
            <ArrowRight size={14} />
          </button>
        </form>
      </dialog>

      <dialog ref={keyDialog} className="app-dialog">
        <div className="dialog-heading">
          <span className="cx-symbol">
            <KeyRound size={18} />
          </span>
          <button className="cx-icon" aria-label="Close" onClick={() => keyDialog.current?.close()}>
            <X size={18} />
          </button>
        </div>
        <h2>Create an API key.</h2>
        <p>
          For {project?.name}. Name it after the agent that uses it: the name is the agent in every
          entry it writes. The secret is shown once.
        </p>
        <form
          key={keyName}
          onSubmit={(event) =>
            submit(event, async (form) => {
              const data = await call(`/projects/${pid}/keys`, "POST", {
                name: form.get("name"),
                days: Number(form.get("days")),
                scopes: String(form.get("access")).split(","),
              });
              setIssued(data);
              if (view === "agents") setAgentKey({ ...data, project: pid });
              keyDialog.current?.close();
              secretDialog.current?.showModal();
              refresh();
            })
          }
        >
          <label>
            Key name
            <input name="name" required maxLength={80} defaultValue={keyName} placeholder="e.g. support-agent" />
          </label>
          <label>
            Access
            <select name="access">
              <option value="memory:read,memory:write">Read and write</option>
              <option value="memory:read">Read only</option>
              <option value="memory:write">Write only</option>
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
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="button" disabled={busy}>
            Create key
            <KeyRound size={14} />
          </button>
        </form>
      </dialog>

      <dialog ref={secretDialog} className="app-dialog secret-dialog" onClose={() => setIssued(null)}>
        <span className="cx-symbol">
          <ShieldCheck size={20} />
        </span>
        <h2>Your key is ready.</h2>
        <p>Copy it now. Once this window closes, the secret cannot be shown again.</p>
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
        <button className="button" onClick={() => secretDialog.current?.close()}>
          I&apos;ve saved my key
          <Check size={14} />
        </button>
      </dialog>

      <dialog ref={factDialog} className="app-dialog memory-dialog">
        <div className="dialog-heading">
          <span className="cx-symbol">
            <Database size={18} />
          </span>
          <button className="cx-icon" aria-label="Close" onClick={() => factDialog.current?.close()}>
            <X size={18} />
          </button>
        </div>
        <h2>{editing ? "Keep the next version." : "Something worth remembering."}</h2>
        <p>
          {editing
            ? "Write the fact as it is now. The earlier version stays in its history."
            : "A structured memory, linked to what it relates to."}
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
              refresh();
              setNotice(editing ? "New version saved. The earlier one is kept." : "Memory saved.");
            })
          }
        >
          <label>
            Key
            <input
              name="key"
              required
              maxLength={100}
              pattern="[A-Za-z0-9][A-Za-z0-9_.:\/\-]{0,99}"
              readOnly={!!editing}
              defaultValue={editing?.key ?? ""}
              placeholder="e.g. customer:acme"
            />
          </label>
          <label>
            Title
            <input name="title" required maxLength={200} defaultValue={editing?.title ?? ""} />
          </label>
          <label>
            Memory
            <textarea name="text" rows={4} maxLength={12000} defaultValue={editing?.text ?? ""} />
          </label>
          <label>
            Metadata <small>JSON object</small>
            <textarea name="metadata" rows={2} defaultValue={JSON.stringify(editing?.metadata ?? {}, null, 2)} />
          </label>
          <label>
            Linked to <small>Keys of other memories, separated by commas</small>
            <input
              name="links"
              defaultValue={
                editing
                  ? current?.summary.edges
                      .filter((edge) => edge.from === editing.key)
                      .map((edge) => edge.to)
                      .join(", ")
                  : ""
              }
              placeholder="e.g. contract:2026, contact:jane"
            />
          </label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="button" disabled={busy}>
            {editing ? "Save new version" : "Save memory"}
            <ArrowRight size={14} />
          </button>
        </form>
      </dialog>

      <dialog ref={dangerDialog} className="app-dialog cx-danger-dialog" onClose={() => setDanger(null)}>
        <div className="dialog-heading">
          <span className="cx-symbol cx-symbol-danger">
            <TriangleAlert size={18} />
          </span>
          <button className="cx-icon" aria-label="Close" onClick={() => dangerDialog.current?.close()}>
            <X size={18} />
          </button>
        </div>
        <h2>{danger?.title}</h2>
        <p>{danger?.text} This cannot be undone.</p>
        <form
          onSubmit={(event) =>
            submit(event, async () => {
              await danger?.act();
              dangerDialog.current?.close();
            })
          }
        >
          <label>
            <span>
              Type <b>{danger?.name}</b> to confirm
            </span>
            <input value={typed} onChange={(event) => setTyped(event.target.value)} autoComplete="off" />
          </label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="button cx-button-danger" disabled={busy || typed !== danger?.name}>
            Delete for good
          </button>
        </form>
      </dialog>
    </div>
  );
}
