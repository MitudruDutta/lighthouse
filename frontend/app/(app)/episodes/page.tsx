import Link from "next/link";
import { Suspense } from "react";

import { Badge, Card, Empty, Loading, RefLink, When, headline } from "@/app/components/ui";
import { type EpisodeSummary, api, segments } from "@/app/lib/api";

const STATES = ["open", "closed", "all"];
const SITUATIONS: [string, string][] = [
  ["", "Every kind"],
  ["port-activity", "Unusual ports"],
  ["berth-overload", "Berth overloads"],
];

export const metadata = { title: "Event history" };

export default function Episodes(props: PageProps<"/episodes">) {
  return (
    <div className="grid gap-5">
      <div>
        <p className="eyebrow mb-3">Intelligence / Event history</p>
        <h1 className="display">Event history<span className="text-[var(--sky)]">.</span></h1>
        <p className="mt-1 text-sm text-muted">
          Source observations and their history. Open a case to review evidence, ownership, and your team’s decisions.
        </p>
      </div>
      <Suspense fallback={<Loading what="episodes" />}>
        <List {...props} />
      </Suspense>
    </div>
  );
}

async function List({ searchParams }: PageProps<"/episodes">) {
  const asked = await searchParams;
  const state = typeof asked.state === "string" && STATES.includes(asked.state) ? asked.state : "all";
  const situation =
    typeof asked.situation === "string" && SITUATIONS.some(([s]) => s === asked.situation) ? asked.situation : "";
  const episodes = await api<EpisodeSummary[]>("/api/episodes", { state, situation, limit: 200 });
  const link = (change: Record<string, string>) =>
    `/episodes?${new URLSearchParams({ state, situation, ...change }).toString()}`;
  return (
    <Card
      title={
        <span className="flex flex-wrap gap-1 normal-case tracking-normal">
          {STATES.map((s) => (
            <Link key={s} href={link({ state: s })} aria-current={s === state ? "page" : undefined} className={s === state ? "badge badge-info" : "badge"}>
              {s}
            </Link>
          ))}
          <span className="mx-1" />
          {SITUATIONS.map(([s, label]) => (
            <Link key={s} href={link({ situation: s })} aria-current={s === situation ? "page" : undefined} className={s === situation ? "badge badge-info" : "badge"}>
              {label}
            </Link>
          ))}
        </span>
      }
      aside={`${episodes.length} shown`}
    >
      {episodes.length === 0 ? (
        <Empty>No recorded cases in this view.</Empty>
      ) : (
        <div>
          <p className="mb-3 text-[11px] text-faint xl:hidden">Scroll sideways for evidence, agent and outcome →</p>
          <div className="overflow-x-auto" role="region" aria-label="Event history" tabIndex={0}>
          <table className="grid episodes-table">
            <thead>
              <tr>
                <th>Opened</th>
                <th>What</th>
                <th>About</th>
                <th>By</th>
                <th className="num">Entries</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {episodes.map((ep) => (
                <tr key={ep.id}>
                  <td>
                    <When at={ep.opened_at} />
                  </td>
                  <td>
                    <Link href={`/episodes/${segments(ep.id)}`} className="link">
                      {headline(ep.id, ep.first)}
                    </Link>
                  </td>
                  <td>
                    {(ep.about ?? []).slice(0, 3).map((r) => (
                      <span key={`${r[0]}${r[1]}`} className="mr-2">
                        <RefLink refer={r} />
                      </span>
                    ))}
                    {(ep.about ?? []).length > 3 ? <span className="text-faint">+{(ep.about ?? []).length - 3}</span> : null}
                  </td>
                  <td className="text-muted">{ep.by}</td>
                  <td className="num">{ep.entry_count}</td>
                  <td>{ep.closed_at ? <Badge tone="closed">Signal cleared</Badge> : <Badge tone="open">Signal open</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </Card>
  );
}
