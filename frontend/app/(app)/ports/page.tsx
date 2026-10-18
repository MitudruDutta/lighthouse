import Link from "next/link";
import { Suspense } from "react";

import { Card, Loading, When } from "@/app/components/ui";
import { PortTable } from "@/app/components/PortTable";
import { PortMaps } from "@/app/components/PortMaps";
import { type Live, type PortRow, type World, api, maybe } from "@/app/lib/api";

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

export const metadata = { title: "World ports" };

export default function Ports(props: PageProps<"/ports">) {
  return (
    <div className="grid gap-5">
      <div><p className="eyebrow mb-3">Operations / World</p><h1 className="display">Ports of the world<span className="text-[var(--sky)]">.</span></h1><p className="mt-2 text-sm text-muted">Explore daily activity and cargo flows. Narrow by country, then compare the ports that matter to you.</p></div>
      <Suspense fallback={<Loading what="the ports" />}>
        <Body {...props} />
      </Suspense>
    </div>
  );
}

async function Body({ searchParams }: PageProps<"/ports">) {
  const asked = (await searchParams).country;
  const country = typeof asked === "string" && /^[A-Z]{3}$/.test(asked) ? asked : undefined;
  const [world, ports, live] = await Promise.all([
    api<World>("/api/world"),
    api<PortRow[]>("/api/ports", { country, limit: 200 }),
    maybe<Live>("/api/live"),
  ]);
  const busiestNow = Object.entries(live?.ports ?? {})
    .filter(([, port]) => port.now > 0)
    .slice(0, 8);
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
      <PortMaps world={world} live={live} />
      {busiestNow.length ? (
        <Card title="Cargo ships and tankers in port now" aside={<>Live AIS · <When at={live?.at} /></>}>
          <ul className="live-ports">
            {busiestNow.map(([key, port]) => (
              <li key={key}>
                <Link href={`/ports/${encodeURIComponent(key)}`} className="link">
                  {port.name}
                </Link>
                <strong>{port.now}</strong>
                <span>
                  ships now · {port.today} today
                </span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      <Card>
        <form action="/ports" className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 xl:grid-cols-[minmax(0,290px)_auto_minmax(0,1fr)]">
          <select name="country" defaultValue={country ?? ""} aria-label="Country" className="min-w-0 w-full">
            <option value="">All countries ({countries.size})</option>
            {sorted.map(([iso3, c]) => (
              <option key={iso3} value={iso3}>
                {c.name} ({c.ports})
              </option>
            ))}
          </select>
          <button type="submit">Show</button>
          <span className="col-span-2 flex flex-wrap gap-1 text-sm xl:col-span-1">
            {QUICK.map(([iso3, name]) => (
              <Link key={iso3} href={`/ports?country=${iso3}`} aria-current={iso3 === country ? "page" : undefined} className={iso3 === country ? "badge badge-info" : "badge"}>
                {name}
              </Link>
            ))}
          </span>
        </form>
      </Card>
      <Card
        title={country ? `Ports in ${countries.get(country)?.name ?? country}` : "Global port directory"}
        aside={<>port calls of <When at={world.newest_day} day /></>}
      >
        <PortTable ports={ports} unusual={world.unusual} />
      </Card>
    </>
  );
}
