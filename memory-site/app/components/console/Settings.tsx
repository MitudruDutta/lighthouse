"use client";
import Link from "next/link";
import { Check, LogOut, ShieldCheck, TriangleAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import GoogleButton from "../GoogleButton";
import { call } from "../../lib/console";
import { LIMITS, PLANS } from "../../lib/plans";
import type { Overview } from "../../lib/types";
import type { State } from "./views";
import { ThemeChoice } from "./ThemeSwitch";
import { CopyButton, Tabs, day } from "./ui";

type Workspace = Overview["workspaces"][number];
export type Danger = { title: string; text: string; name: string; act: () => Promise<void> };
type Tab = "project" | "workspace" | "profile";
const ZONES = [
  "UTC",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Los_Angeles",
];

function Form({
  submit,
  children,
}: {
  submit: (form: FormData) => Promise<void>;
  children: React.ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");
        try {
          await submit(new FormData(event.currentTarget));
        } catch (err) {
          setError(err instanceof Error ? err.message : "Please try again.");
        } finally {
          setBusy(false);
        }
      }}
    >
      {children}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <button className="button button-small" disabled={busy}>
        Save
        <Check size={14} />
      </button>
    </form>
  );
}

export function SettingsView({
  s,
  tab: first,
  workspace,
  workspaces,
  setUser,
  renamed,
  danger,
  deleteProject,
  deleteWorkspace,
}: {
  s: State;
  tab: string;
  workspace?: Workspace;
  workspaces: Workspace[];
  setUser: (user: Overview["user"]) => void;
  renamed: (kind: "project" | "workspace", value: Record<string, string>) => void;
  danger: (danger: Danger) => void;
  deleteProject: () => Promise<void>;
  deleteWorkspace: () => Promise<void>;
}) {
  const router = useRouter();
  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }
  const [tab, setTab] = useState<Tab>(
    first === "workspace" || first === "profile" ? first : s.project ? "project" : "workspace",
  );
  return (
    <div className="cx-settings">
      <Tabs
        label="Settings"
        items={[
          ["project", "Project"],
          ["workspace", "Workspace"],
          ["profile", "Profile"],
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "project" ? (
        s.project ? (
          <>
            <section className="cx-panel">
              <header className="cx-panel-head">
                <h2>General</h2>
              </header>
              <Form
                submit={async (form) => {
                  const result = await call(`/projects/${s.project?.id}`, "PATCH", {
                    name: form.get("name"),
                    description: form.get("description"),
                  });
                  renamed("project", result);
                  s.notify("Project saved.");
                }}
              >
                <label>
                  Project name
                  <input name="name" required maxLength={80} defaultValue={s.project.name} />
                </label>
                <label>
                  Description <small>Optional</small>
                  <textarea name="description" rows={3} maxLength={400} defaultValue={s.project.description} />
                </label>
                <label>
                  Project ID
                  <span className="cx-field-copy">
                    <code>{s.project.id}</code>
                    <CopyButton value={s.project.id} />
                  </span>
                </label>
              </Form>
            </section>
            <section className="cx-panel cx-danger-zone">
              <header className="cx-panel-head">
                <div>
                  <h2>
                    <TriangleAlert size={15} /> Delete this project
                  </h2>
                  <p>
                    Deletes its graph with every memory and version, its API keys, and its usage.
                    Agents using its keys stop working at once. This cannot be undone.
                  </p>
                </div>
                <button
                  className="button button-small cx-button-danger"
                  onClick={() =>
                    danger({
                      title: `Delete ${s.project?.name}?`,
                      text: "Its graph, keys, and usage are deleted for good.",
                      name: s.project?.name ?? "",
                      act: deleteProject,
                    })
                  }
                >
                  Delete project
                </button>
              </header>
            </section>
          </>
        ) : (
          <section className="cx-panel">
            <p className="cx-muted">This workspace has no project yet.</p>
          </section>
        )
      ) : null}
      {tab === "workspace" && workspace ? (
        <>
          <section className="cx-panel">
            <header className="cx-panel-head">
              <h2>Workspace</h2>
            </header>
            <Form
              submit={async (form) => {
                const result = await call(`/workspaces/${workspace.id}`, "PATCH", {
                  name: form.get("name"),
                });
                renamed("workspace", result);
                s.notify("Workspace saved.");
              }}
            >
              <label>
                Workspace name
                <input name="name" required maxLength={80} defaultValue={workspace.name} key={workspace.id} />
              </label>
            </Form>
          </section>
          <section className="cx-panel cx-danger-zone">
            <header className="cx-panel-head">
              <div>
                <h2>
                  <TriangleAlert size={15} /> Delete this workspace
                </h2>
                <p>
                  {workspaces.length < 2
                    ? "Your only workspace cannot be deleted. Create another one first."
                    : `Deletes ${s.projects.length} project${s.projects.length === 1 ? "" : "s"} with their graphs, keys, and usage. This cannot be undone.`}
                </p>
              </div>
              <button
                className="button button-small cx-button-danger"
                disabled={workspaces.length < 2}
                onClick={() =>
                  danger({
                    title: `Delete ${workspace.name}?`,
                    text: `Every project in it is deleted for good: ${s.projects.length}.`,
                    name: workspace.name,
                    act: deleteWorkspace,
                  })
                }
              >
                Delete workspace
              </button>
            </header>
          </section>
        </>
      ) : null}
      {tab === "profile" ? (
        <>
          <section className="cx-panel cx-profile-card">
            <span className="cx-avatar cx-avatar-large">{s.user.name[0]?.toUpperCase()}</span>
            <div>
              <h2>{s.user.name}</h2>
              <p>{s.user.email}</p>
              <ul>
                <li>{s.user.created ? `Member since ${day(s.user.created, s.user.timezone)}` : "Member"}</li>
                <li>
                  {workspaces.length} workspace{workspaces.length === 1 ? "" : "s"}
                </li>
                <li>
                  {s.projects.length} project{s.projects.length === 1 ? "" : "s"} here
                </li>
                <li data-tone={s.user.google_connected ? "good" : undefined}>
                  {s.user.google_connected ? "Google connected" : "Password sign-in"}
                </li>
              </ul>
            </div>
          </section>
          <section className="cx-panel">
            <header className="cx-panel-head">
              <div>
                <h2>Details</h2>
                <p>Your name is shown to you in the console; times are shown in your time zone.</p>
              </div>
            </header>
            <Form
              submit={async (form) => {
                setUser({ ...s.user, ...(await call("/profile", "PATCH", Object.fromEntries(form))) });
                s.notify("Profile saved.");
              }}
            >
              <label>
                Name
                <input name="name" defaultValue={s.user.name} required maxLength={80} />
              </label>
              <label>
                Email address
                <input value={s.user.email} disabled readOnly />
              </label>
              <label>
                Time zone
                <input name="timezone" defaultValue={s.user.timezone} required list="cx-zones" />
                <datalist id="cx-zones">
                  {ZONES.map((zone) => (
                    <option key={zone} value={zone} />
                  ))}
                </datalist>
              </label>
            </Form>
          </section>
          <section className="cx-panel">
            <header className="cx-panel-head">
              <div>
                <h2>Appearance</h2>
                <p>System follows your device. The choice is kept by this browser.</p>
              </div>
            </header>
            <ThemeChoice />
          </section>
          <section className="cx-panel">
            <header className="cx-panel-head">
              <div>
                <h2>Sign-in</h2>
                <p>
                  {s.user.google_connected
                    ? "Google is connected to this account; you can also sign in with your password."
                    : "Connect the Google account with this email for faster sign-in."}
                </p>
              </div>
              <button className="button button-outline button-small" onClick={signOut}>
                <LogOut size={14} />
                Sign out
              </button>
            </header>
            {s.user.google_connected ? (
              <p className="cx-google">
                <Check size={15} /> Google connected · {s.user.email}
              </p>
            ) : (
              <GoogleButton connect />
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}

function Meter({ label, used, most }: { label: string; used: number; most: number }) {
  return (
    <div className="cx-meter">
      <span>
        {label}
        <b>
          {used} / {most}
        </b>
      </span>
      <i>
        <em style={{ width: `${Math.min(100, (used / most) * 100)}%` }} />
      </i>
    </div>
  );
}

export function PlanView({
  s,
  workspaces,
  docs,
}: {
  s: State;
  workspaces: Workspace[];
  docs: string;
}) {
  const live = s.keys.filter((key) => !key.revoked && key.expires > s.clock).length;
  return (
    <>
      <section className="cx-panel cx-plan-current">
        <div>
          <span className="cx-eyebrow">Current plan</span>
          <h2>Developer</h2>
          <p>Free during the preview. Billing is not active: no card, no charges.</p>
        </div>
        <div className="cx-meters">
          <Meter label="Workspaces" used={workspaces.length} most={LIMITS.workspaces} />
          <Meter label="Projects in this workspace" used={s.projects.length} most={LIMITS.projectsPerWorkspace} />
          <Meter label="Active keys in this project" used={live} most={LIMITS.keysPerProject} />
          <p>
            Each key may send {LIMITS.requestsPerMinute} requests a minute; a request over the limit
            gets a 429 and can be sent again a moment later.
          </p>
        </div>
      </section>
      <div className="cx-plans">
        {PLANS.map((plan) => (
          <article key={plan.id} className="cx-plan" data-current={plan.current || undefined}>
            <header>
              <h3>{plan.name}</h3>
              {plan.current ? <span className="cx-pill" data-tone="good">Current</span> : null}
              {plan.soon ? <span className="cx-pill">Coming soon</span> : null}
            </header>
            <p className="cx-price">
              <strong>{plan.price}</strong> <span>{plan.cadence}</span>
            </p>
            <p>{plan.summary}</p>
            <ul>
              {plan.features.map((feature) => (
                <li key={feature}>
                  <Check size={13} />
                  {feature}
                </li>
              ))}
            </ul>
            {plan.href === "docs" ? (
              <a className="button button-outline button-small" href={`${docs}/library`}>
                {plan.action}
              </a>
            ) : plan.current ? (
              <Link className="button button-outline button-small" href={s.href("agents")}>
                Connect an agent
              </Link>
            ) : (
              <button className="button button-outline button-small" disabled>
                {plan.action}
              </button>
            )}
          </article>
        ))}
      </div>
      <p className="cx-note">
        <ShieldCheck size={15} />
        The library is free under Apache-2.0 whatever you choose: run it on your own FalkorDB at no cost.
      </p>
    </>
  );
}
