import Link from "next/link";
import { Suspense } from "react";

import { Card, Loading, RefLink, When } from "@/app/components/ui";
import { type PortCall, api, segments } from "@/app/lib/api";

const SHOWN = ["eta", "etd", "ata", "atd", "area", "areas"];
const RELATIONS: Record<string, [string, string]> = {
  MADE_BY: ["Vessel", "Vessel"],
  CALLS_AT: ["Port", "Calls at"],
  AT: ["Berth", "Berth"],
  CAME_FROM: ["Port", "Came from"],
  BOUND_FOR: ["Port", "Bound for"],
};

export default function PortCallPage(props: PageProps<"/portcalls/[id]">) {
  return (
    <Suspense fallback={<Loading what="the port call" />}>
      <Body {...props} />
    </Suspense>
  );
}

function value(v: unknown) {
  return typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v) ? <When at={v} /> : v === undefined ? "—" : String(v);
}

async function Body({ params, searchParams }: PageProps<"/portcalls/[id]">) {
  const id = (await params).id;
  const asked = (await searchParams).at;
  const at = typeof asked === "string" && asked ? new Date(asked).toISOString() : undefined;
  const call = await api<PortCall>(`/api/portcalls/${encodeURIComponent(id)}`, { at });
  return (
    <div className="grid gap-5">
      <div>
        <h1 className="serif text-3xl">Port call {call.key}</h1>
        <form className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <label htmlFor="at" className="text-muted">
            As it was at
          </label>
          <input id="at" name="at" type="datetime-local" defaultValue={at ? at.slice(0, 16) : ""} />
          <button type="submit">Look</button>
          {at ? (
            <Link href={`/portcalls/${call.key}`} className="link">
              now
            </Link>
          ) : null}
        </form>
      </div>
      <div className="grid gap-5 md:grid-cols-2">
        <Card title={<>Values at <When at={call.at} /></>}>
          {call.values ? (
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
              {SHOWN.map((name) => (
                <div key={name} className="contents">
                  <dt className="text-muted">{name}</dt>
                  <dd>{value(call.values![name])}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-sm text-faint">Not known at that time.</p>
          )}
        </Card>
        <Card title="Pointed at, then">
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            {Object.entries(RELATIONS).map(([relation, [label, text]]) => (
              <div key={relation} className="contents">
                <dt className="text-muted">{text}</dt>
                <dd>
                  {(call.relations[relation] ?? []).map((key) => (
                    <RefLink key={String(key)} refer={[label, key]}>
                      {String(key)}
                    </RefLink>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>
      <Card title="Every version" aside={`${call.versions.length}`}>
        <div className="overflow-x-auto">
          <table className="grid">
            <thead>
              <tr>
                <th>From</th>
                <th>Until</th>
                {SHOWN.slice(0, 4).map((name) => (
                  <th key={name}>{name}</th>
                ))}
                <th>By</th>
              </tr>
            </thead>
            <tbody>
              {call.versions.map((v, i) => (
                <tr key={i}>
                  <td>{value(v.valid_from)}</td>
                  <td>{value(v.valid_to)}</td>
                  {SHOWN.slice(0, 4).map((name) => (
                    <td key={name}>{value(v[name])}</td>
                  ))}
                  <td className="text-muted">{String(v.by)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {call.episodes.length ? (
        <Card title="Episodes about it">
          <ul className="grid gap-1 text-sm">
            {call.episodes.map((ep) => (
              <li key={ep.id}>
                <Link href={`/episodes/${segments(ep.id)}`} className="link">
                  {ep.id}
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
