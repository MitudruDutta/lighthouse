import Link from "next/link";
import { Suspense } from "react";

import { WorldMap } from "./components/WorldMap";
import { Badge, Card, Empty, Loading, RefLink, Stat, When, number } from "./components/ui";
import { type Berth, type EpisodeSummary, type Lesson, type Status, type World, api, segments } from "./lib/api";

export default function Overview() {
  return (
    <div className="grid gap-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Ports of the world, watched</h1>
        <p className="mt-1 text-sm text-muted">
          Port calls of Finland every few minutes, and of 2,000 ports in 180 countries every day. Agents
          watch both, act on what is unusual, and learn from what ends.
        </p>
      </div>
      <Suspense fallback={<Loading what="the graph" />}>
        <Stats />
      </Suspense>
      <Suspense fallback={<Loading what="the ports of the world" />}>
        <Map />
      </Suspense>
      <div className="grid gap-5 md:grid-cols-2">
        <Suspense fallback={<Loading what="unusual ports" />}>
          <UnusualPorts />
        </Suspense>
        <Suspense fallback={<Loading what="berths" />}>
          <Overloads />
        </Suspense>
      </div>
      <Suspense fallback={<Loading what="lessons" />}>
        <Learned />
      </Suspense>
    </div>
  );
}

async function Stats() {
  const status = await api<Status>("/api/status");
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Stat
        label="Ports"
        value={number(status.counts.Port)}
        note={<>last read of the world <When at={status.last_world_poll?.at} /></>}
      />
      <Stat
        label="Port calls in Finland"
        value={number(status.counts.PortCall)}
        note={<>last read <When at={status.last_poll?.at} /></>}
      />
      <Stat label="Open episodes" value={number(status.open_episodes)} note={`${number(status.counts.Episode)} in all`} />
      <Stat label="Lessons" value={number(status.counts.Lesson)} note={`${number(status.counts.Playbook)} playbooks`} />
    </div>
  );
}

async function Map() {
  const world = await api<World>("/api/world");
  const unusual = Object.keys(world.unusual).length;
  return (
    <Card
      title="Port calls on the last day"
      aside={
        <>
          {number(world.ports.length)} ports · day <When at={world.newest_day} day /> · {unusual} unusual now
        </>
      }
    >
      <WorldMap world={world} />
      <p className="mt-2 text-xs text-faint">
        Each dot is a port, as large as its port calls that day. Red: a port whose port calls fell to half its
        usual or rose to twice it.
      </p>
    </Card>
  );
}

async function UnusualPorts() {
  const episodes = await api<EpisodeSummary[]>("/api/episodes", {
    state: "open",
    situation: "port-activity",
    limit: 12,
  });
  return (
    <Card title="Unusual ports now" aside={<Link href="/episodes?situation=port-activity&state=open" className="link">all</Link>}>
      {episodes.length === 0 ? (
        <Empty>No port is unusual now.</Empty>
      ) : (
        <ul className="grid gap-2">
          {episodes.map((ep) => {
            const port = ep.about?.find(([label]) => label === "Port");
            const state = String(ep.first?.state ?? "");
            return (
              <li key={ep.id} className="flex items-center justify-between gap-3 text-sm">
                <span>
                  {port ? <RefLink refer={port}>{String(ep.first?.name ?? port[1])}</RefLink> : null}{" "}
                  <Badge tone={state}>{state}</Badge>{" "}
                  <span className="text-xs text-muted">
                    {number(ep.first?.calls)} port calls, usually {number(ep.first?.usual, 1)}
                  </span>
                </span>
                <Link href={`/episodes/${segments(ep.id)}`} className="link shrink-0 text-xs">
                  since <When at={ep.opened_at} day />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

async function Overloads() {
  const berths = await api<Berth[]>("/api/berths");
  const over = berths.filter((b) => b.overload);
  return (
    <Card title="Finnish berths with more ships expected than ever held" aside={<Link href="/berths" className="link">board</Link>}>
      {over.length === 0 ? (
        <Empty>No berth is overloaded now.</Empty>
      ) : (
        <ul className="grid gap-2">
          {over.slice(0, 8).map((b) => (
            <li key={b.berth} className="flex items-center justify-between gap-3 text-sm">
              <RefLink refer={["Berth", b.berth]}>{b.name ?? b.berth}</RefLink>
              <span className="text-xs text-muted">
                <Badge tone="busy">{b.overload!.most} expected</Badge> held {b.capacity}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

async function Learned() {
  const lessons = await api<Lesson[]>("/api/lessons");
  return (
    <Card title="Learned from what ended" aside={<Link href="/learned" className="link">all</Link>}>
      {lessons.length === 0 ? (
        <Empty>Nothing learned yet: lessons come from episodes that ended.</Empty>
      ) : (
        <ul className="grid gap-2">
          {lessons.slice(0, 6).map((lesson) => (
            <li key={lesson.id} className="text-sm">
              <Badge tone="recall">{lesson.weight}</Badge> {lesson.statement}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
