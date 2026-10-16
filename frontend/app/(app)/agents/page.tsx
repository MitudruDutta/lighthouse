import { Suspense } from "react";
import Link from "next/link";
import type { Metadata } from "next";
import {
  ArrowUpRight,
  BookOpenCheck,
  Bot,
  Clock3,
  Radar,
  Radio,
  Workflow,
} from "lucide-react";
import { Loading, When, ago } from "@/app/components/ui";
import { agentName, said } from "@/app/components/words";
import {
  api,
  type Activity,
  type Intelligence,
  type Status,
} from "@/app/lib/api";
import { isFresh, utcTime } from "@/app/lib/freshness";
import { caseHref } from "@/app/lib/operations";
export const metadata: Metadata = { title: "Agent activity" };
export default function Agents() {
  return (
    <Suspense fallback={<Loading what="agent activity" />}>
      <Body />
    </Suspense>
  );
}
async function Body() {
  const [status, found, activity] = await Promise.all([
    api<Status>("/api/status"),
    api<Intelligence>("/api/intelligence"),
    api<Activity>("/api/activity", { limit: 15 }),
  ]);
  const now = utcTime(status.now);
  const feed =
    isFresh(status.last_poll?.at, status.now, 15) && status.availability.feed;
  const world =
    isFresh(status.last_world_poll?.at, status.now, 90) &&
    status.availability.portwatch;
  const desk =
    status.availability.desk && isFresh(status.last_desk?.at, status.now, 5);
  const agents = [
    {
      name: "Arrival watcher",
      kind: "Rules · after each arrival import",
      text: "Flags expected berth overlaps and preserves the observations behind them.",
      icon: Radar,
      at: status.last_poll?.at,
      state: feed ? "Checked recently" : "Awaiting update",
      to: "/berths",
      metric: `${status.counts.Berth ?? 0} berths in memory`,
    },
    {
      name: "Global trend watcher",
      kind: "Rules · after new daily observations",
      text: "Compares daily activity with each port's recent baseline. Observation dates stay attached.",
      icon: Radio,
      at: status.last_world_poll?.at,
      state: world ? "Source checked" : "Awaiting update",
      to: "/ports",
      metric: `Observations through ${status.last_world_poll?.newest ?? "—"}`,
    },
    {
      name: "Desk investigator",
      kind: "AI · graph tools & connected evidence",
      text: "Investigates queued signals, reads supporting history, and records an assessment for your review.",
      icon: Bot,
      at: status.last_desk?.at,
      state: !desk
        ? "Awaiting service"
        : found.tasks.claimed
          ? "Investigating"
          : "Ready",
      to: "/desk",
      metric: `${found.assessments.total} assessments recorded`,
    },
    {
      name: "Outcome reviewer",
      kind: "Rules · after completed source episodes",
      text: "Finds recurring outcomes and preserves supporting or contradicting evidence as lessons.",
      icon: BookOpenCheck,
      at: status.last_poll?.at,
      state: feed ? "Scheduled with imports" : "Awaiting update",
      to: "/learned",
      metric: `${status.counts.Lesson ?? 0} lessons · ${status.counts.Playbook ?? 0} playbooks`,
    },
  ];
  return (
    <div className="ops-workspace">
      <header className="ops-page-heading">
        <div>
          <p className="ops-kicker">Behind every investigation</p>
          <h1>Work you can follow.</h1>
          <p>
            See what observed the signal, what investigated it, and what became
            a lesson.
          </p>
        </div>
        <Link href="/desk" className="ops-primary">
          Review investigations
          <ArrowUpRight size={17} />
        </Link>
      </header>
      <section className="ops-activity-banner">
        <Workflow size={32} />
        <div>
          <h2>Evidence moves forward. You make the decision.</h2>
          <p>
            Watchers detect signals. Desk investigates. Your team records the
            next step and outcome.
          </p>
        </div>
        <Link href="/dashboard">Open attention queue →</Link>
      </section>
      <section className="ops-agent-grid" aria-label="Agent activity">
        {agents.map((a, i) => (
          <article key={a.name} className="ops-agent">
            <header>
              <i>
                <a.icon size={23} />
              </i>
              <span>{a.state}</span>
            </header>
            <p className="ops-kicker">
              0{i + 1} / {a.kind}
            </p>
            <h2>{a.name}</h2>
            <p>{a.text}</p>
            <strong>{a.metric}</strong>
            <footer>
              <span>
                <Clock3 size={13} />
                {a.at ? ago(a.at, now) : "No completed check"}
              </span>
              <Link href={a.to}>
                Inspect work
                <ArrowUpRight size={15} />
              </Link>
            </footer>
          </article>
        ))}
      </section>
      <div className="ops-activity-layout">
        <section className="ops-panel">
          <div className="ops-panel-heading">
            <span>Latest recorded work</span>
            <span className="ops-subtle">
              From the source evidence timeline
            </span>
          </div>
          <ol className="ops-timeline">
            {activity.entries.map((e) => (
              <li key={e.id}>
                <i>
                  <Radio size={14} />
                </i>
                <div>
                  <strong>{agentName(e.by)}</strong>
                  <p>{said(e)}</p>
                  <small>
                    <When at={String(e.recorded_at ?? e.at)} />
                  </small>
                  <Link href={caseHref(e.episode)}>
                    Open related case
                    <ArrowUpRight size={13} />
                  </Link>
                </div>
              </li>
            ))}
          </ol>
        </section>
        <aside className="ops-panel ops-activity-explainer">
          <p className="ops-kicker">Read the numbers correctly</p>
          <h2>Investigation isn’t resolution.</h2>
          <p>
            {found.tasks.done ?? 0} automation tasks have finished. That
            includes signals that cleared before investigation.
          </p>
          <div>
            <strong>{found.assessments.total}</strong>
            <span>Desk assessments recorded</span>
          </div>
          <div>
            <strong>{found.tasks.claimed ?? 0}</strong>
            <span>Tasks currently claimed by an agent</span>
          </div>
          <p>
            A human resolution appears only after someone records an outcome on
            the case.
          </p>
          <Link href="/desk" className="ops-outline">
            Review case outcomes
            <ArrowUpRight size={14} />
          </Link>
        </aside>
      </div>
    </div>
  );
}
