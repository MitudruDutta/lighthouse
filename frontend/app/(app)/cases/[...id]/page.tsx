import { createHash } from "node:crypto";
import { Suspense } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  Clock3,
  Compass,
  GitBranch,
  MessageSquare,
  ShieldCheck,
  Star,
  UserRound,
  Waves,
} from "lucide-react";
import {
  Card,
  Loading,
  Prose,
  RefLink,
  Trace,
  When,
} from "@/app/components/ui";
import { agentName, said } from "@/app/components/words";
import CaseActions from "@/app/components/operations/CaseActions";
import { desk, type Message, type ModelChoice } from "@/app/lib/api";
import { STATUS, caseHref, type CaseDetail } from "@/app/lib/operations";
import { utcTime } from "@/app/lib/freshness";
import { operations, operationsToken } from "@/app/lib/operations-server";
import { Ask } from "../../desk/forms";
export default function CasePage(props: PageProps<"/cases/[...id]">) {
  return (
    <Suspense fallback={<Loading what="this case" />}>
      <Body {...props} />
    </Suspense>
  );
}
async function Body({ params }: PageProps<"/cases/[...id]">) {
  const id = (await params).id.map(decodeURIComponent).join("/");
  const token = await operationsToken();
  const detail = await operations<CaseDetail>(
    `case?id=${encodeURIComponent(id)}`,
  );
  if (!detail || !token)
    return (
      <Card title="Case unavailable">
        <p>This case may be unavailable, or you may need to sign in again.</p>
        <Link href="/login" className="ops-primary mt-4">
          Open your workspace →
        </Link>
      </Card>
    );
  const item = detail.case;
  const session =
    "case_" + createHash("sha256").update(id).digest("hex").slice(0, 32);
  const [history, models] = await Promise.all([
    desk<Message[]>(`/api/desk/sessions/${session}`, token),
    desk<ModelChoice[]>("/api/desk/models", token),
  ]);
  const messages = history.ok ? history.data : [];
  const choices = models.ok ? models.data : [];
  const observation = [...detail.source.entries]
    .reverse()
    .find((e) => e.type === "observation");
  const steps = [
    { label: "Signal observed", done: true },
    { label: "Desk assessment", done: !!item.assessment },
    { label: "Human decision", done: !!item.action },
    { label: "Outcome recorded", done: item.status === "resolved" },
  ];
  const timeline = [
    ...detail.events.map((e) => ({
      key: `decision-${e.revision}`,
      human: true,
      by: e.by,
      at: e.at,
      text: e.text,
      label:
        (
          {
            claim: "Case claimed",
            release: "Returned to queue",
            propose: "Next step proposed",
            approve: "Plan approved",
            resolve: "Outcome recorded",
            reopen: "Case reopened",
          } as Record<string, string>
        )[e.operation] ?? "Decision recorded",
    })),
    ...detail.source.entries.map((e) => ({
      key: e.id,
      human: false,
      by: agentName(e.by),
      at: String(e.recorded_at ?? e.at),
      text: said(e),
      label:
        e.type === "assessment"
          ? "Desk assessment recorded"
          : e.type === "outcome"
            ? "Source signal cleared"
            : e.type === "observation"
              ? "Source observation"
              : e.type === "recall"
                ? "Relevant lesson recalled"
                : "Investigation handed to Desk",
    })),
  ].sort((a, b) => utcTime(b.at) - utcTime(a.at));
  return (
    <div className="ops-case-page">
      <Link href="/desk" className="ops-back">
        <ArrowLeft size={16} />
        Case files
      </Link>
      <header className="ops-case-heading">
        <div>
          <p className="ops-kicker">
            {item.scope === "global"
              ? "Global port trend"
              : "Finnish arrival coordination"}
          </p>
          <h1>{item.title}</h1>
          <p>{item.impact}</p>
        </div>
        <span className={`ops-status ${item.status}`}>
          {STATUS[item.status]}
        </span>
      </header>
      <div className="ops-case-progress" aria-label="Case progress">
        {steps.map((step, i) => (
          <div key={step.label} className={step.done ? "done" : ""}>
            <i>{step.done ? <Check size={15} /> : i + 1}</i>
            <span>{step.label}</span>
          </div>
        ))}
      </div>
      <div className="ops-case-layout">
        <div className="ops-case-main">
          <section className="ops-panel ops-assessment">
            <div className="ops-panel-heading">
              <span>
                <ShieldCheck size={18} />
                What needs your judgment
              </span>
              <span className="ops-subtle">
                {item.assessment ? "Desk assessment" : "Source signal"}
              </span>
            </div>
            {item.assessment ? (
              <>
                <Prose text={String(item.assessment.text)} />
                <Trace found={item.assessment} />
              </>
            ) : (
              <>
                <h2>Review the evidence before choosing a next step.</h2>
                <p>
                  {item.scope === "global"
                    ? "This is a daily activity signal. Use its observation date when assessing relevance to today's operations."
                    : "Expected overlap exceeds the number of ships previously observed together. Confirm timing and berth arrangements with the responsible coordinator."}
                </p>
              </>
            )}
            {item.source_cleared ? (
              <div className="ops-inline-notice">
                The source signal has cleared. Your team’s review and recorded
                outcome remain separate.
              </div>
            ) : null}
          </section>
          <section className="ops-panel">
            <div className="ops-panel-heading">
              <span>
                <GitBranch size={18} />
                Evidence behind the signal
              </span>
              <Link
                href={`/investigate?kind=Episode&key=${encodeURIComponent(id)}`}
              >
                Explore connections
                <ArrowUpRight size={14} />
              </Link>
            </div>
            <div className="ops-evidence-facts">
              <div>
                <span>Observation date</span>
                <strong>
                  <When
                    at={item.observation_at}
                    day={item.scope === "global"}
                    timezone={detail.profile.timezone}
                  />
                </strong>
              </div>
              <div>
                <span>Source</span>
                <strong>
                  {item.scope === "global"
                    ? "IMF PortWatch · daily estimates"
                    : "Fintraffic · arrival reports"}
                </strong>
              </div>
              <div>
                <span>Reported signal</span>
                <strong>{item.impact}</strong>
              </div>
            </div>
            {observation ? (
              <div className="ops-evidence-summary">{said(observation)}</div>
            ) : null}
            <div className="ops-evidence-links">
              {item.about.slice(0, 12).map((ref) => (
                <RefLink key={ref.join(":")} refer={ref} />
              ))}
            </div>
            <Link href="/sources" className="ops-source-link">
              Check source dates and coverage
              <ArrowUpRight size={14} />
            </Link>
          </section>
          {detail.prior_outcomes.length ? (
            <section className="ops-panel">
              <div className="ops-panel-heading">
                <span>
                  <Clock3 size={18} />
                  What happened here before
                </span>
                <span className="ops-subtle">
                  Your team’s recorded outcomes
                </span>
              </div>
              <div className="ops-prior-outcomes">
                {detail.prior_outcomes.map((previous) => (
                  <article key={previous.id}>
                    <p>{previous.outcome}</p>
                    {previous.action ? (
                      <small>Plan: {previous.action}</small>
                    ) : null}
                    <Link href={caseHref(previous.id)}>
                      Revisit the decision
                      <ArrowUpRight size={14} />
                    </Link>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
          <section id="case-conversation" className="ops-panel">
            <div className="ops-panel-heading">
              <span>
                <MessageSquare size={18} />
                Discuss this case
              </span>
              <span className="ops-subtle">Your conversation</span>
            </div>
            <p className="ops-panel-intro">
              The Desk starts with this case’s evidence. Ask what changed, check
              its reasoning, or explore a possible next step.
            </p>
            <ol className="ops-conversation">
              {messages.map((m) => (
                <li key={m.seq} className={m.role}>
                  <span>{m.role === "user" ? "You" : "Desk"}</span>
                  <Prose text={m.text} />
                  {m.role === "assistant" ? <Trace found={m} /> : null}
                </li>
              ))}
            </ol>
            <Ask
              session={session}
              fresh={!messages.length}
              models={choices}
              selected={choices[0]?.id}
              caseId={id}
              unavailable={!models.ok}
            />
          </section>
          <section className="ops-panel">
            <div className="ops-panel-heading">
              <span>
                <Clock3 size={18} />
                Case history
              </span>
              <span className="ops-subtle">Evidence and decisions</span>
            </div>
            <ol className="ops-timeline">
              {timeline.map((e) => (
                <li key={e.key}>
                  <i className={e.human ? "human" : ""}>
                    {e.human ? <UserRound size={14} /> : <Waves size={14} />}
                  </i>
                  <div>
                    <strong>{e.label}</strong>
                    {e.text ? <p>{e.text}</p> : null}
                    <small>
                      {e.human && e.by === detail.user ? "You" : e.by} ·{" "}
                      <When at={e.at} timezone={detail.profile.timezone} />
                    </small>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>
        <aside className="ops-case-rail" aria-label="Case actions">
          <section className="ops-panel ops-decision">
            <p className="ops-kicker">Move this case forward</p>
            <h2>
              {item.status === "resolved"
                ? "Outcome recorded."
                : item.owner
                  ? "Your next decision."
                  : "Give this case an owner."}
            </h2>
            <div className="ops-owner-summary">
              <UserRound size={17} />
              <span>
                {item.owner
                  ? item.mine
                    ? "You're responsible for this case"
                    : `Assigned to ${item.owner}`
                  : "Nobody has taken ownership yet"}
              </span>
            </div>
            {item.action ? (
              <div className="ops-plan">
                <span>
                  {item.action_status === "approved"
                    ? "Approved plan"
                    : "Proposed plan"}
                </span>
                <p>{item.action}</p>
              </div>
            ) : null}
            {item.outcome ? (
              <div className="ops-plan outcome">
                <span>Recorded outcome</span>
                <p>{item.outcome}</p>
              </div>
            ) : null}
            <CaseActions item={item} />
          </section>
          <section className="ops-rail-note">
            <Compass size={21} />
            <h3>Keep evidence in view.</h3>
            <p>
              {item.scope === "global"
                ? "Global estimates describe the observation day. They do not establish live port conditions."
                : "Historical overlap is a signal to investigate. It is not an official berth-capacity limit."}
            </p>
            <Link href="/profile">
              <Star size={14} />
              Manage your watchlist
              <ArrowUpRight size={14} />
            </Link>
          </section>
        </aside>
      </div>
    </div>
  );
}
