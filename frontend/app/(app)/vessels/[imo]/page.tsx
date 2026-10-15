import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Card, Empty, Loading, Title, When } from "@/app/components/ui";
import { type Vessel, api } from "@/app/lib/api";

export const metadata: Metadata = { title: "Ship" };

export default function VesselPage(props: PageProps<"/vessels/[imo]">) {
  return (
    <Suspense fallback={<Loading what="the ship" />}>
      <Body {...props} />
    </Suspense>
  );
}

async function Body({ params }: PageProps<"/vessels/[imo]">) {
  const imo = (await params).imo;
  const vessel = await api<Vessel>(`/api/vessels/${encodeURIComponent(imo)}`);
  const now = vessel.versions.at(-1) ?? {};
  return (
    <div className="grid gap-6">
      <Title lead={`IMO number ${vessel.key}${now.nationality ? `, flag ${String(now.nationality)}` : ""}${now.mmsi ? `, MMSI ${String(now.mmsi)}` : ""}`}>
        {String(now.name ?? vessel.key)}
      </Title>
      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Port calls in Finland">
          {vessel.port_calls.length === 0 ? (
            <Empty>No port call of this ship is known now.</Empty>
          ) : (
            <ul className="grid gap-1.5 text-sm">
              {vessel.port_calls.map((id) => (
                <li key={id}>
                  <Link href={`/portcalls/${id}`} className="link">
                    Port call {id}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Names and details over time" aside={`${vessel.versions.length} versions`}>
          <ol className="grid gap-3 text-sm">
            {vessel.versions.map((v, n) => (
              <li key={n}>
                <div className="font-medium">{String(v.name ?? "")}</div>
                <div className="text-xs text-muted">
                  from <When at={String(v.valid_from)} /> {v.valid_to ? <>until <When at={String(v.valid_to)} /></> : "until now"}
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}
