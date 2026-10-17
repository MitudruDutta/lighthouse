"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CheckCheck,
  Compass,
  Filter,
  Radio,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
  Waves,
  Pause,
  Play,
} from "lucide-react";
import { active, caseHref, STATUS, type Queue } from "@/app/lib/operations";
import { utcTime } from "@/app/lib/freshness";
import { excerpt, plain } from "@/app/components/words";

function date(value: string, timezone: string, clock = false) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    timeZone: value.includes("T") ? timezone : "UTC",
    ...(clock
      ? {
          hour: "2-digit" as const,
          minute: "2-digit" as const,
          timeZoneName: "short" as const,
        }
      : {}),
  }).format(new Date(utcTime(value)));
}
export default function CaseBoard({
  queue,
  now,
  globalDay,
  feedAt,
  investigations = false,
}: {
  queue: Queue;
  now: string;
  globalDay?: string | null;
  feedAt?: string | null;
  investigations?: boolean;
}) {
  const [view, setView] = useState<string>(queue.profile.view ?? "attention");
  const [scope, setScope] = useState(queue.profile.focus);
  const [search, setSearch] = useState("");
  const [visible, setVisible] = useState(8);
  const [paused, setPaused] = useState(false);
  const open = queue.cases.filter(active);
  const mine = open.filter((c) => c.mine);
  const reviewed = open.filter((c) => c.status === "needs_review");
  const resolved = queue.cases.filter((c) => c.status === "resolved");
  const filtered = queue.cases.filter((c) => {
    const inView =
      view === "all" ||
      (view === "attention" && active(c)) ||
      (view === "review" && c.status === "needs_review") ||
      (view === "mine" && c.mine && active(c)) ||
      (view === "watching" && c.watching && active(c)) ||
      (view === "resolved" && c.status === "resolved") ||
      (view === "source_cleared" && c.status === "source_cleared");
    return (
      inView &&
      (scope === "all" || c.scope === scope) &&
      `${c.title} ${c.impact} ${c.owner ?? ""}`
        .toLowerCase()
        .includes(search.toLowerCase())
    );
  });
  const lag = globalDay
    ? Math.max(
        0,
        Math.floor((utcTime(now.slice(0, 10)) - utcTime(globalDay)) / 86400000),
      )
    : null;
  return (
    <div className="ops-workspace">
      <header className="ops-page-heading">
        <div>
          <p className="ops-kicker">
            {investigations
              ? "Your team's decision desk"
              : `Good to see you, ${queue.profile.name}`}
          </p>
          <h1>
            {investigations ? "Case files" : "Make the next move count."}
          </h1>
          <p>
            {investigations
              ? "Every signal has a story. Give it an owner, a decision, and an outcome."
              : "Know what changed. See the evidence. Take the next step."}
          </p>
        </div>
        <Link className="ops-outline" href="/profile">
          <Star size={17} />
          My watchlist
          <span>
            {queue.profile.ports.length + queue.profile.vessels.length}
          </span>
        </Link>
      </header>
      {!investigations ? (
        <section
          className="ops-command"
          aria-label="Attention summary"
          data-paused={paused}
        >
          <div className="ops-command-copy">
            <span className="ops-live">
              <i />
              OPERATIONS BRIEF
            </span>
            <div className="ops-brief-number">
              {open.length.toLocaleString("en")}
              <span>
                cases need
                <br />a next step.
              </span>
            </div>
            <p>
              {reviewed.length
                ? `${reviewed.length} assessments ready for your review.`
                : "New signals enter the queue with their supporting evidence."}{" "}
              {mine.length
                ? `You're leading ${mine.length}.`
                : "Pick a case and take ownership."}
            </p>
            <div className="ops-command-actions">
              <button
                onClick={() => {
                  setView("attention");
                  setScope("all");
                  document
                    .getElementById("case-queue")
                    ?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
              >
                Review attention queue
                <ArrowDownRight size={18} />
              </button>
              <Link href="/desk/chat">
                Ask the desk
                <ArrowUpRight size={16} />
              </Link>
            </div>
          </div>
          <div className="ops-orbit" aria-hidden="true">
            <div className="ops-orbit-ring" />
            <div className="ops-orbit-ring second" />
            <div className="ops-orbit-line" />
            <div className="ops-beacon">
              <Waves size={38} />
            </div>
            <div className="ops-orbit-label one">
              <Radio size={14} />
              Signals observed
            </div>
            <div className="ops-orbit-label two">
              <Sparkles size={14} />
              Evidence connected
            </div>
            <div className="ops-orbit-label three">
              <ShieldCheck size={14} />
              You decide the next step
            </div>
            <span className="ops-orbit-caption">
              OBSERVE / INVESTIGATE / DECIDE
            </span>
          </div>
          <button
            className="ops-motion-toggle"
            aria-label={
              paused
                ? "Resume workspace animation"
                : "Pause workspace animation"
            }
            aria-pressed={paused}
            onClick={() => setPaused(!paused)}
          >
            {paused ? <Play size={13} /> : <Pause size={13} />}
          </button>
        </section>
      ) : (
        <section className="ops-investigation-brief">
          <ShieldCheck size={26} />
          <div>
            <h2>Clear ownership. Decisions you can revisit.</h2>
            <p>
              Review a case, agree on the next step, and preserve what happened.
            </p>
          </div>
          <span>{open.length} active cases</span>
        </section>
      )}
      <section className="ops-metrics" aria-label="Your case queue">
        <button onClick={() => setView("attention")}>
          <span>Needs attention</span>
          <strong>{open.length}</strong>
          <small>Across the latest case history</small>
        </button>
        <button onClick={() => setView("mine")}>
          <span>Assigned to you</span>
          <strong>{mine.length}</strong>
          <small>Keep your work moving</small>
        </button>
        <button onClick={() => setView("review")}>
          <span>Ready for review</span>
          <strong>{reviewed.length}</strong>
          <small>Assessment or next step proposed</small>
        </button>
        <button onClick={() => setView("resolved")}>
          <span>Outcomes recorded</span>
          <strong>{resolved.length}</strong>
          <small>Human-reviewed resolutions</small>
        </button>
      </section>
      <div className="ops-data-strip">
        <span>
          <Radio size={15} />
          Finnish arrivals{" "}
          <strong>
            {feedAt
              ? `checked ${date(feedAt, queue.profile.timezone, true)}`
              : "awaiting update"}
          </strong>
        </span>
        <span>
          <Compass size={15} />
          Global observations{" "}
          <strong>
            {globalDay
              ? date(globalDay, queue.profile.timezone)
              : "awaiting data"}
          </strong>
          {lag !== null && lag > 0 ? <b>{lag} days behind today</b> : null}
        </span>
        <Link href="/sources">
          View source dates
          <ArrowUpRight size={14} />
        </Link>
      </div>
      <section id="case-queue" className="ops-queue">
        <div className="ops-section-heading">
          <div>
            <p className="ops-kicker">Your next decisions</p>
            <h2>
              {view === "mine"
                ? "Your active cases"
                : view === "watching"
                  ? "From your watchlist"
                  : view === "resolved"
                    ? "Recorded outcomes"
                    : view === "source_cleared"
                      ? "Signals cleared by the source"
                      : "Attention, with context."}
            </h2>
          </div>
          <span>
            {filtered.length} cases{queue.limited ? " · latest 200" : ""}
          </span>
        </div>
        <div className="ops-filters">
          <div className="ops-tabs" aria-label="Case view">
            {[
              ["attention", "Needs attention"],
              ["review", "Needs review"],
              ["mine", "Mine"],
              ["watching", "Watching"],
              ["resolved", "Resolved"],
              ["source_cleared", "Source cleared"],
              ["all", "All"],
            ].map(([id, label]) => (
              <button
                key={id}
                aria-pressed={view === id}
                onClick={() => setView(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="ops-filter-inputs">
            <label>
              <Search size={16} />
              <input
                aria-label="Search cases"
                placeholder="Find a case…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <label>
              <Filter size={15} />
              <select
                aria-label="Case coverage"
                value={scope}
                onChange={(e) => setScope(e.target.value as typeof scope)}
              >
                <option value="all">All coverage</option>
                <option value="finland">Finnish arrivals</option>
                <option value="global">Global trends</option>
              </select>
            </label>
          </div>
        </div>
        {view === "watching" &&
        !queue.profile.ports.length &&
        !queue.profile.vessels.length ? (
          <div className="ops-empty">
            <Star size={28} />
            <h3>Make this desk yours.</h3>
            <p>Follow ports and vessels to bring their cases into focus.</p>
            <Link href="/profile" className="ops-primary">
              Build your watchlist
              <ArrowRight size={16} />
            </Link>
          </div>
        ) : filtered.length ? (
          <div className="ops-case-grid">
            {filtered.slice(0, visible).map((c) => {
              const age = Math.max(
                0,
                Math.floor(
                  (utcTime(now.slice(0, 10)) -
                    utcTime(c.observation_at.slice(0, 10))) /
                    86400000,
                ),
              );
              return (
                <Link
                  href={caseHref(c.id)}
                  key={c.id}
                  className={`ops-case-card ${c.scope === "global" ? "global" : "arrivals"}`}
                >
                  <div className="ops-case-top">
                    <span className="ops-case-category">
                      {c.scope === "global" ? (
                        <Compass size={15} />
                      ) : (
                        <Waves size={15} />
                      )}
                      {c.scope === "global"
                        ? "Daily port trend"
                        : "Arrival overlap"}
                    </span>
                    <span className={`ops-status ${c.status}`}>
                      {STATUS[c.status]}
                    </span>
                  </div>
                  <h3>{c.title}</h3>
                  <p className="ops-case-impact">{c.impact}</p>
                  <div className="ops-case-evidence">
                    <span>
                      <ShieldCheck size={14} />
                      {c.assessment
                        ? "Desk assessment available"
                        : "Source evidence attached"}
                    </span>
                    {age > 1 ? (
                      <span className="ops-aged">Observed {age} days ago</span>
                    ) : (
                      <span>
                        Observed{" "}
                        {date(c.observation_at, queue.profile.timezone)}
                      </span>
                    )}
                  </div>
                  {c.action ? (
                    <div className="ops-next-step">
                      <small>
                        {c.action_status === "approved"
                          ? "Approved next step"
                          : "Proposed next step"}
                      </small>
                      <p>{c.action}</p>
                    </div>
                  ) : c.assessment ? (
                    <p className="ops-case-excerpt">
                      {excerpt(plain(String(c.assessment.text)), 185)}
                    </p>
                  ) : (
                    <p className="ops-case-excerpt">
                      Review the observation and connected history before
                      deciding what happens next.
                    </p>
                  )}
                  <div className="ops-case-bottom">
                    <span className="ops-owner">
                      <i>{(c.owner ?? "?").slice(0, 1).toUpperCase()}</i>
                      {c.owner
                        ? c.mine
                          ? "Assigned to you"
                          : c.owner
                        : "Unassigned"}
                      {c.watching ? (
                        <Star size={13} fill="currentColor" />
                      ) : null}
                    </span>
                    <span>
                      {c.status === "resolved" ? "View outcome" : "Open case"}
                      <ArrowUpRight size={16} />
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        ) : (
          <div className="ops-empty">
            <CheckCheck size={30} />
            <h3>
              {view === "resolved"
                ? "Outcomes will appear here."
                : "Nothing in this view."}
            </h3>
            <p>
              {view === "resolved"
                ? "Resolve a case with a short explanation to preserve your team's decision."
                : "Change a filter or explore the full attention queue."}
            </p>
            <button
              className="ops-outline"
              onClick={() => {
                setView("attention");
                setScope("all");
                setSearch("");
              }}
            >
              Show attention queue
              <ArrowRight size={16} />
            </button>
          </div>
        )}
        {filtered.length > visible ? (
          <div className="ops-load-more">
            <button
              className="ops-outline"
              onClick={() => setVisible(visible + 8)}
            >
              Show more cases
              <ArrowDownRight size={16} />
            </button>
            <span>
              Showing {Math.min(visible, filtered.length)} of {filtered.length}
            </span>
          </div>
        ) : null}
      </section>
    </div>
  );
}
