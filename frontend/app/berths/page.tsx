import Link from "next/link";
import { Suspense } from "react";

import { Badge, Card, Empty, Loading, When } from "../components/ui";
import { type Berth, api } from "../lib/api";

export default function Berths() {
  return (
    <div className="grid gap-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Finnish berths</h1>
        <p className="mt-1 text-sm text-muted">
          What each berth held at one time, from the port calls that were alongside together, and where more port
          calls are expected than that. Overloaded berths first.
        </p>
      </div>
      <Suspense fallback={<Loading what="the berths" />}>
        <Board />
      </Suspense>
    </div>
  );
}

async function Board() {
  const berths = await api<Berth[]>("/api/berths");
  if (berths.length === 0) return <Empty>No berth has port calls yet.</Empty>;
  return (
    <Card title="Berth board" aside={`${berths.length} berths`}>
      <div className="overflow-x-auto">
        <table className="grid">
          <thead>
            <tr>
              <th>Berth</th>
              <th>Area</th>
              <th className="num">Held at once</th>
              <th>Expected</th>
              <th>Port calls</th>
            </tr>
          </thead>
          <tbody>
            {berths.map((b) => (
              <tr key={b.berth} id={b.berth}>
                <td>
                  <div>{b.name ?? b.berth}</div>
                  <div className="text-xs text-faint">{b.berth}</div>
                </td>
                <td className="text-muted">{b.area}</td>
                <td className="num">{b.capacity}</td>
                <td>
                  {b.overload ? (
                    <>
                      <Badge tone="busy">{`${b.overload.most} at once`}</Badge>
                      <div className="mt-1 text-xs text-muted">
                        <When at={b.overload.from} /> to <When at={b.overload.until} />
                      </div>
                    </>
                  ) : (
                    <span className="text-faint">within what it held</span>
                  )}
                </td>
                <td className="text-sm">
                  {(b.overload?.calls ?? []).map((id) => (
                    <Link key={id} href={`/portcalls/${id}`} className="link mr-2">
                      {id}
                    </Link>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
