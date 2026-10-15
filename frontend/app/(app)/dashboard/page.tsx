import {
  ArrowUpRight,
  BookOpenCheck,
  Eye,
  Flag,
  Globe2,
  GitBranch,
  Inbox,
  type LucideIcon,
  MessagesSquare,
  Radar,
  Send,
  Ship,
  Sparkles,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { Suspense } from "react";

import { WorldMap } from "@/app/components/WorldMap";
import { Prose, Trace, When, ago, number } from "@/app/components/ui";
import { agentName, said } from "@/app/components/words";
import {
  type Activity,
  type Berth,
  type DeskInbox,
  type Lesson,
  type Status,
  type Unusual,
  type World,
  api,
  maybe,
  segments,
} from "@/app/lib/api";
import { isFresh, utcTime } from "@/app/lib/freshness";

export const metadata: Metadata = { title: "Overview" };

export default function Dashboard() {
  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-3">Operations / Overview</p>
          <h1 className="display">The port desk<span className="text-[var(--sky)]">.</span></h1>
          <p className="mt-2 max-w-[62ch] text-sm text-muted">A world of port activity. One place to see what needs attention.</p>
        </div>
        <Link href="/desk/chat" className="button inline-flex items-center gap-2 text-sm">
          <MessagesSquare size={16} aria-hidden /> Ask the desk
        </Link>
      </div>
      <Suspense fallback={null}><SourceNotice /></Suspense>
      <Link href="/agents" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--edge)] bg-[var(--info-bg)] px-4 py-3 text-xs"><span className="flex items-center gap-2"><GitBranch size={15} className="text-[var(--sky)]" aria-hidden /><strong>Connected decisions. Shared memory.</strong><span className="hidden text-muted lg:inline">Inspect the crew, native graph algorithms, and the evidence behind each action.</span></span><span className="link font-medium">Enter agent control room ↗</span></Link>
      <Suspense fallback={<Skeleton className="h-[132px]" />}>
        <Figures />
      </Suspense>
      <div className="grid items-start gap-6 xl:grid-cols-12">
        <div className="xl:col-span-8">
          <Suspense fallback={<Skeleton className="h-[460px]" />}>
            <MapCard />
          </Suspense>
        </div>
        <div className="xl:col-span-4">
          <Suspense fallback={<Skeleton className="h-[460px]" />}>
            <UnusualCard />
          </Suspense>
        </div>
      </div>
      <div className="grid items-start gap-6 xl:grid-cols-12">
        <div className="grid gap-6 xl:col-span-7">
          <Suspense fallback={<Skeleton className="h-[380px]" />}>
            <BerthsCard />
          </Suspense>
          <Suspense fallback={<Skeleton className="h-[320px]" />}>
            <ActivityCard />
          </Suspense>
        </div>
        <div className="grid gap-6 xl:col-span-5">
          <Suspense fallback={<Skeleton className="h-[380px]" />}>
            <DeskCard />
          </Suspense>
          <Suspense fallback={<Skeleton className="h-[320px]" />}>
            <LearnedCard />
          </Suspense>
        </div>
      </div>
    </div>
  );
}

async function SourceNotice() {
  const [status, world] = await Promise.all([maybe<Status>("/api/status"), maybe<World>("/api/world")]);
  if (!status || !world) return <div className="rounded-lg border border-[var(--coral)] p-4 text-sm">Data connection unavailable. <Link href="/sources" className="link">Check source health →</Link></div>;
  const fresh = isFresh(status.last_poll?.at, status.now, 15) && status.availability.feed;
  return <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
    <span className="flex flex-wrap items-center gap-x-4 gap-y-2"><span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full" style={{ background: fresh ? "var(--mint)" : "var(--coral)" }} />{fresh ? "Arrivals synced" : "Arrivals delayed"} {ago(status.last_poll?.at, utcTime(status.now))}</span><span>Global activity as of <When at={world.newest_day} day /></span></span>
    <Link href="/sources" className="link font-medium">Data health <ArrowUpRight size={11} className="inline" aria-hidden /></Link>
  </div>;
}

function Skeleton({ className }: { className: string }) {
  return <div className={`card animate-pulse ${className}`} aria-hidden />;
}

function Panel({
  icon: Icon,
  title,
  link,
  children,
  tint = "var(--sky-text)",
}: {
  icon: LucideIcon;
  title: string;
  link?: [string, string];
  children: ReactNode;
  tint?: string;
}) {
  return (
    <section className="card">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex min-w-0 items-center gap-2.5 text-[15px] font-semibold">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg" style={{ background: "var(--rule-soft)", color: tint }}>
            <Icon size={15} aria-hidden />
          </span>
          {title}
        </h2>
        {link ? (
          <Link href={link[0]} className="ml-auto flex shrink-0 items-center gap-1 text-xs text-muted hover:text-[var(--ink)]">
            {link[1]} <ArrowUpRight size={13} aria-hidden />
          </Link>
        ) : null}
      </header>
      {children}
    </section>
  );
}

async function Figures() {
  const [status, world, berths, inbox] = await Promise.all([
    api<Status>("/api/status"),
    api<World>("/api/world"),
    api<Berth[]>("/api/berths"),
    api<DeskInbox>("/api/desk", { limit: 1 }),
  ]);
  const countries = new Set(world.ports.map((p) => p[2]).filter(Boolean)).size;
  const unusual = Object.keys(world.unusual).length;
  const over = berths.filter((b) => b.overload).length;
  const figures: { icon: LucideIcon; tint: string; value: number; label: string; note: ReactNode; to: string }[] = [
    {
      icon: Globe2,
      tint: "var(--sky-text)",
      value: world.ports.length,
      label: "Ports on the map",
      note: `Across ${countries} countries`,
      to: "/ports",
    },
    {
      icon: Radar,
      tint: "var(--beam)",
      value: unusual,
      label: "Unusual port activity",
      note: "On the latest available source day",
      to: "/episodes?situation=port-activity&state=open",
    },
    {
      icon: Ship,
      tint: "var(--coral)",
      value: over,
      label: "Berth overload signals",
      note: `of ${berths.length} Finnish berths with ships due`,
      to: "/berths",
    },
    {
      icon: Inbox,
      tint: "var(--violet)",
      value: inbox.waiting_count,
      label: "Desk handoffs pending",
      note: status.availability.desk ? "Queued for investigation" : "Investigations temporarily unavailable",
      to: "/desk",
    },
  ];
  return (
    <section aria-label="Figures" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {figures.map(({ icon: Icon, tint, value, label, note, to }) => (
        <Link key={label} href={to} className="card metric-card group flex flex-col gap-4 transition-colors">
          <span className="flex items-center justify-between">
            <span className="grid h-9 w-9 place-items-center rounded-xl" style={{ background: "var(--rule-soft)", color: tint }}>
              <Icon size={18} aria-hidden />
            </span>
            <ArrowUpRight size={16} className="text-faint transition-colors group-hover:text-[var(--ink)]" aria-hidden />
          </span>
          <span>
            <span className="display tabular block text-[42px] leading-none" style={{ color: "var(--ink)" }}>
              {number(value)}
            </span>
            <span className="mt-2 block text-xs font-semibold">{label}</span>
            <span className="mt-1 block text-[10px] text-faint">{note}</span>
          </span>
        </Link>
      ))}
    </section>
  );
}

async function MapCard() {
  const world = await api<World>("/api/world");
  return (
    <Panel icon={Globe2} title="Global port activity" link={["/ports", "Explore ports"]}>
      <WorldMap world={world} />
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ background: "var(--sky)" }} aria-hidden /> a port, as large as its
          port calls that day
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ background: "var(--coral)" }} aria-hidden /> unusual: half or
          twice its usual
        </span>
        <span className="text-faint">Daily observations, published with a delay.</span>
      </div>
    </Panel>
  );
}

const DID: Record<string, [LucideIcon, string]> = {
  observation: [Eye, "var(--sky-text)"],
  recall: [BookOpenCheck, "var(--violet)"],
  action: [Send, "var(--beam)"],
  assessment: [Sparkles, "var(--mint)"],
  outcome: [Flag, "var(--ink-2)"],
};

async function ActivityCard() {
  const [activity, status] = await Promise.all([
    api<Activity>("/api/activity", { limit: 9 }),
    api<Status>("/api/status"),
  ]);
  const now = new Date(`${status.now.replace(/Z$/, "")}Z`).getTime();
  const most = Math.max(1, ...activity.opened.map((d) => d.count));
  return (
    <Panel icon={Radar} title="Agent activity" link={["/episodes", "All episodes"]} tint="var(--mint)">
      {activity.entries.length === 0 ? (
        <p className="py-8 text-center text-sm text-faint">The agents have written nothing yet.</p>
      ) : (
        <ol className="activity-list" aria-label="Recent agent activity">
          {activity.entries.map((entry) => {
            const [Icon, tint] = DID[entry.type] ?? [Eye, "var(--ink-2)"];
            return (
              <li key={entry.id}>
                <Link
                  href={`/episodes/${segments(entry.episode)}`}
                  className="activity-row"
                >
                  <span className="activity-icon" style={{ color: tint }}>
                    <Icon size={14} aria-hidden />
                  </span>
                  <span className="activity-body">
                    <span className="activity-description">{said(entry)}</span>
                    <span className="activity-meta">
                      <span>{agentName(entry.by)}</span><span aria-hidden>·</span><span>{ago(String(entry.recorded_at ?? entry.at), now)}</span>
                    </span>
                  </span>
                  <ArrowUpRight size={13} className="activity-arrow" aria-hidden />
                </Link>
              </li>
            );
          })}
        </ol>
      )}
      {activity.opened.length ? (
        <div className="mt-4 border-t pt-3" style={{ borderColor: "var(--edge)" }}>
          <p className="mb-2 text-[11px] text-faint">Episodes opened by day</p>
          <div className="flex h-12 items-end gap-1">
            {activity.opened.map((d) => (
              <div key={d.day} className="group relative flex-1" title={`${d.day}: ${d.count} episodes`}>
                <div className="rounded-t-[3px]" style={{ height: `${Math.max(6, (d.count / most) * 48)}px`, background: "var(--sky)", opacity: 0.85 }} />
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </Panel>
  );
}

async function UnusualCard() {
  const [found, world] = await Promise.all([
    api<{ ports: Unusual[] }>("/api/unusual", { limit: 4 }),
    api<World>("/api/world"),
  ]);
  const country = new Map(world.ports.map((p) => [p[0], p[3]]));
  return (
    <Panel icon={Radar} title="Attention needed" link={["/episodes?situation=port-activity&state=open", "View all"]} tint="var(--coral)">
      <p className="mb-3 text-[11px] text-faint">Open signals · latest source day <When at={world.newest_day} day /></p>
      {found.ports.length === 0 ? (
        <p className="py-8 text-center text-sm text-faint">Every port is within its usual.</p>
      ) : (
        <ul className="grid gap-1">
          {found.ports.map((p) => {
            const scale = Math.max(p.calls, p.usual * 2, 1);
            return (
              <li key={p.episode}>
                <Link
                  href={`/ports/${encodeURIComponent(p.port)}`}
                  className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 border-b py-3.5 hover:bg-[var(--rule-soft)]" style={{ borderColor: "var(--edge)" }}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{p.name ?? p.port}</span>
                    <span className="block truncate text-xs text-faint">{country.get(p.port) ?? p.port}</span>
                  </span>
                  <span className="badge badge-quiet">{p.state === "quiet" ? "↓ Quiet" : "↑ Busy"}</span>
                  <span className="col-span-2 grid gap-1.5" aria-label={`${p.calls} port calls against a usual ${p.usual}`}>
                    <span className="relative h-2 rounded-full" style={{ background: "var(--rule-soft)" }}>
                      <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${(p.calls / scale) * 100}%`, background: "var(--beam)" }} />
                      <span className="absolute -inset-y-1 w-0.5 rounded" style={{ left: `${(p.usual / scale) * 100}%`, background: "var(--ink)" }} />
                    </span>
                    <span className="text-[11px] text-faint">
                      {number(p.calls)} ships, usually {number(p.usual, 1)}
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

async function BerthsCard() {
  const berths = await api<Berth[]>("/api/berths");
  const over = berths.filter((b) => b.overload);
  return (
    <Panel icon={Ship} title="Berth overload signals" link={["/berths", "Berth board"]} tint="var(--coral)">
      <p className="mb-2 text-[11px] text-faint">Expected overlap exceeds the highest overlap observed in this graph.</p>
      {over.length === 0 ? (
        <p className="py-8 text-center text-sm text-faint">No berth expects more ships than it ever held.</p>
      ) : (
        <ul className="grid gap-1">
          {over.slice(0, 4).map((b) => (
            <li key={b.berth}>
              <Link href={`/berths/${segments(b.berth)}`} className="flex items-center justify-between gap-3 rounded-lg px-2 py-2.5 hover:bg-[var(--rule-soft)]">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{b.name ?? b.berth}</span>
                  <span className="block text-xs text-faint">
                    from <When at={b.overload!.from} />
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1" aria-label={`${b.overload!.most} ships expected, ${b.capacity} held`}>
                  {Array.from({ length: Math.min(b.overload!.most, 6) }, (_, n) => (
                    <Ship key={n} size={15} aria-hidden style={{ color: n < b.capacity ? "var(--ink-2)" : "var(--coral)" }} />
                  ))}
                  <span className="ml-1 text-xs text-muted">
                    {b.overload!.most} due, held {b.capacity}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

async function DeskCard() {
  const [inbox, status] = await Promise.all([api<DeskInbox>("/api/desk", { limit: 2 }), api<Status>("/api/status")]);
  return (
    <Panel icon={Sparkles} title="Desk investigations" link={["/desk", "Open inbox"]} tint="var(--mint)">
      {inbox.assessed.length === 0 ? (
        <div className="py-6 text-center">
          <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-xl bg-[var(--info-bg)] text-[var(--mint)]"><Sparkles size={23} aria-hidden /></div>
          <p className="text-sm font-semibold">{status.availability.desk ? "Ready for the first conclusion" : "Investigations temporarily unavailable"}</p>
          <p className="mx-auto mt-1 max-w-[46ch] text-xs text-faint">
            It reads each episode the Watchers hand over, looks further with the tools it picks, and writes what it
            concludes here, checked against the graph.
          </p>
          <Link href="/desk" className="button-quiet mt-4 !text-xs">View pending handoffs →</Link>
        </div>
      ) : (
        <ol className="grid gap-5">
          {inbox.assessed.map((a) => (
            <li key={a.id}>
              <Link href={`/episodes/${segments(a.episode)}`} className="mb-1.5 block truncate text-xs text-faint hover:text-[var(--ink)]">
                {a.episode}
              </Link>
              <div className="max-h-40 overflow-hidden [mask-image:linear-gradient(black_70%,transparent)]">
                <Prose text={a.text} />
              </div>
              <Trace found={a} />
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

async function LearnedCard() {
  const lessons = await api<Lesson[]>("/api/lessons");
  const most = Math.max(1, ...lessons.map((l) => l.weight));
  return (
    <Panel icon={BookOpenCheck} title="Lessons from past episodes" link={["/learned", "Memory library"]} tint="var(--violet)">
      {lessons.length === 0 ? (
        <p className="py-8 text-center text-sm text-faint">Nothing yet. A lesson needs three episodes that ended alike.</p>
      ) : (
        <ul className="grid gap-3">
          {lessons.slice(0, 5).map((l) => (
            <li key={l.id} className="grid gap-1.5">
              <span className="text-sm leading-snug">{l.statement}</span>
              <span className="flex items-center gap-2">
                <span className="h-1.5 flex-1 rounded-full" style={{ background: "var(--rule-soft)" }}>
                  <span className="block h-full rounded-full" style={{ width: `${Math.max(0, (l.weight / most) * 100)}%`, background: "var(--violet)" }} />
                </span>
                <span className="text-[11px] text-faint">weight {l.weight}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
