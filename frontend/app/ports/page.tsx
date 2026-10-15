import Link from "next/link";
import { Suspense } from "react";

import { Badge, Card, Empty, Loading, When, number } from "../components/ui";
import { type PortRow, type World, api } from "../lib/api";

const QUICK = [
  ["IND", "India"],
  ["CHN", "China"],
  ["SGP", "Singapore"],
  ["JPN", "Japan"],
  ["ARE", "UAE"],
  ["USA", "United States"],
  ["BRA", "Brazil"],
  ["NGA", "Nigeria"],
  ["NLD", "Netherlands"],
  ["FIN", "Finland"],
];

export default function Ports(props: PageProps<"/ports">) {
  return (
    <div className="grid gap-5">
      <h1 className="text-2xl font-semibold tracking-tight">Ports of the world</h1>
      <Suspense fallback={<Loading what="the ports" />}>
        <Body {...props} />
      </Suspense>
    </div>
  );
}

async function Body({ searchParams }: PageProps<"/ports">) {
  const asked = (await searchParams).country;
  const country = typeof asked === "string" && /^[A-Z]{3}$/.test(asked) ? asked : undefined;
  const [world, ports] = await Promise.all([
    api<World>("/api/world"),
    api<PortRow[]>("/api/ports", { country, limit: 200 }),
  ]);
  const countries = new Map<string, { name: string; ports: number }>();
  for (const [, , iso3, name] of world.ports) {
    if (!iso3) continue;
    const found = countries.get(iso3) ?? { name: name ?? iso3, ports: 0 };
    found.ports += 1;
    countries.set(iso3, found);
  }
  const sorted = [...countries.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name));
  return (
    <>
      <Card>
        <form action="/ports" className="flex flex-wrap items-center gap-2">
          <select name="country" defaultValue={country ?? ""} aria-label="Country">
            <option value="">All countries ({countries.size})</option>
            {sorted.map(([iso3, c]) => (
              <option key={iso3} value={iso3}>
                {c.name} ({c.ports})
              </option>
            ))}
          </select>
          <button type="submit">Show</button>
          <span className="ml-2 flex flex-wrap gap-1 text-sm">
            {QUICK.map(([iso3, name]) => (
              <Link key={iso3} href={`/ports?country=${iso3}`} className={iso3 === country ? "badge badge-info" : "badge"}>
                {name}
              </Link>
            ))}
          </span>
        </form>
      </Card>
      <Card
        title={country ? `${countries.get(country)?.name ?? country}: busiest first` : "Busiest ports of the world"}
        aside={<>port calls of <When at={world.newest_day} day /></>}
      >
        {ports.length === 0 ? (
          <Empty>No port with port calls here.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="grid">
              <thead>
                <tr>
                  <th>Port</th>
                  <th>Country</th>
                  <th className="num">Port calls</th>
                  <th className="num">Container</th>
                  <th className="num">Tanker</th>
                  <th className="num">Dry bulk</th>
                  <th className="num">Unloaded t</th>
                  <th className="num">Loaded t</th>
                </tr>
              </thead>
              <tbody>
                {ports.map((p) => (
                  <tr key={p.key}>
                    <td>
                      <Link href={`/ports/${encodeURIComponent(p.key)}`} className="link">
                        {p.name ?? p.key}
                      </Link>{" "}
                      {p.key in world.unusual ? <Badge tone="hot">unusual</Badge> : null}
                    </td>
                    <td className="text-muted">{p.country}</td>
                    <td className="num">{number(p.calls)}</td>
                    <td className="num">{number(p.calls_container)}</td>
                    <td className="num">{number(p.calls_tanker)}</td>
                    <td className="num">{number(p.calls_dry_bulk)}</td>
                    <td className="num">{number(p.import_tonnes)}</td>
                    <td className="num">{number(p.export_tonnes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
