import Link from "next/link";
import { Suspense } from "react";

import { Bars } from "../../components/Bars";
import { Badge, Card, Empty, Loading, When, number } from "../../components/ui";
import { type Port, api, segments } from "../../lib/api";

export default function PortPage(props: PageProps<"/ports/[key]">) {
  return (
    <Suspense fallback={<Loading what="the port" />}>
      <Body {...props} />
    </Suspense>
  );
}

const KINDS: [keyof Port["days"][number], string][] = [
  ["calls_container", "Container"],
  ["calls_tanker", "Tanker"],
  ["calls_dry_bulk", "Dry bulk"],
  ["calls_general_cargo", "General cargo"],
  ["calls_roro", "Ro-ro"],
];

async function Body({ params }: PageProps<"/ports/[key]">) {
  const key = decodeURIComponent((await params).key);
  const port = await api<Port>(`/api/ports/${encodeURIComponent(key)}`, { days: 60 });
  const last = port.days.at(-1);
  const feed = Object.entries(port.port_calls).filter(([, calls]) => calls.length);
  return (
    <div className="grid gap-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{port.place.name ?? key}</h1>
        <p className="mt-1 text-sm text-muted">
          {port.place.country} {port.place.continent ? `· ${port.place.continent}` : null} · {key}
        </p>
      </div>
      {last ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="card">
            <div className="text-xs uppercase tracking-wide text-muted">Port calls on <When at={last.day} day /></div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">{number(last.calls)}</div>
          </div>
          <div className="card">
            <div className="text-xs uppercase tracking-wide text-muted">Unloaded / loaded</div>
            <div className="mt-1 text-lg font-semibold tabular-nums">
              {number(last.import_tonnes)} / {number(last.export_tonnes)} t
            </div>
          </div>
          <div className="card md:col-span-2">
            <div className="text-xs uppercase tracking-wide text-muted">By type of ship</div>
            <div className="mt-2 flex flex-wrap gap-2 text-sm">
              {KINDS.map(([field, label]) => (
                <span key={field}>
                  {label} <b className="tabular-nums">{number(last[field])}</b>
                </span>
              ))}
            </div>
          </div>
        </div>
      ) : null}
      <Card title="Port calls by day" aside={`${port.days.length} days`}>
        {port.days.length ? <Bars days={port.days} /> : <Empty>PortWatch has no days of this port.</Empty>}
      </Card>
      <div className="grid gap-5 md:grid-cols-2">
        <Card title="Episodes">
          {port.episodes.length === 0 ? (
            <Empty>Nothing unusual was seen here.</Empty>
          ) : (
            <ul className="grid gap-2 text-sm">
              {port.episodes.map((ep) => (
                <li key={ep.id} className="flex justify-between gap-3">
                  <Link href={`/episodes/${segments(ep.id)}`} className="link">
                    <When at={ep.opened_at} day />
                  </Link>
                  {ep.outcome ? <Badge tone="closed">{`back in ${String(ep.outcome.days)} days`}</Badge> : <Badge tone="open">open</Badge>}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Learned about this port">
          {port.lessons.length === 0 ? (
            <Empty>Nothing learned yet.</Empty>
          ) : (
            <ul className="grid gap-2 text-sm">
              {port.lessons.map((lesson) => (
                <li key={lesson.id}>
                  <Badge tone="recall">{lesson.weight}</Badge> {lesson.statement}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      {feed.length ? (
        <Card title="Ships in the Finnish feed that touch this port">
          <ul className="grid gap-2 text-sm">
            {feed.map(([relation, calls]) => (
              <li key={relation}>
                <span className="text-muted">
                  {{ CALLS_AT: "Calling here", CAME_FROM: "Came from here", BOUND_FOR: "Bound here" }[relation] ?? relation}:
                </span>{" "}
                {calls.slice(0, 30).map((id) => (
                  <Link key={id} href={`/portcalls/${id}`} className="link mr-2">
                    {id}
                  </Link>
                ))}
                {calls.length > 30 ? <span className="text-faint">and {calls.length - 30} more</span> : null}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
