import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Badge, Card, Empty, Loading, Title, When } from "@/app/components/ui";
import { type BerthPage, api, segments } from "@/app/lib/api";

export const metadata: Metadata = { title: "Berth" };

export default function Berth(props: PageProps<"/berths/[...key]">) {
  return (
    <Suspense fallback={<Loading what="the berth" />}>
      <Body {...props} />
    </Suspense>
  );
}

async function Body({ params }: PageProps<"/berths/[...key]">) {
  const key = (await params).key.map(decodeURIComponent).join("/");
  const berth = await api<BerthPage>(`/api/berths/${segments(key)}`);
  const now = berth.versions.at(-1) ?? {};
  return (
    <div className="grid gap-6">
      <Title lead={`${String(now.area_name ?? now.area ?? "")} ${key}`.trim()}>{String(now.name ?? key)}</Title>
      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Port calls here now" aside={`${berth.port_calls.length}`}>
          {berth.port_calls.length === 0 ? (
            <Empty>No port call is expected at this berth now.</Empty>
          ) : (
            <ul className="grid grid-cols-2 gap-1.5 text-sm sm:grid-cols-3">
              {berth.port_calls.map((id) => (
                <li key={id}>
                  <Link href={`/portcalls/${id}`} className="link">
                    {id}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="What was learned here">
          {berth.lessons.length === 0 ? (
            <Empty>Nothing yet. A lesson needs three overloads here that ended the same way.</Empty>
          ) : (
            <ul className="grid gap-2 text-sm">
              {berth.lessons.map((l) => (
                <li key={l.id}>
                  <Badge tone="recall">{l.weight}</Badge> {l.statement}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <Card title="Episodes at this berth" aside={`${berth.episodes.length}`}>
        {berth.episodes.length === 0 ? (
          <Empty>This berth has never had more ships expected than it held.</Empty>
        ) : (
          <ul className="grid gap-2 text-sm">
            {berth.episodes.map((ep) => (
              <li key={ep.id} className="flex flex-wrap justify-between gap-3">
                <Link href={`/episodes/${segments(ep.id)}`} className="link">
                  Opened <When at={ep.opened_at} />
                </Link>
                {ep.closed_at ? <Badge tone="closed">ended</Badge> : <Badge tone="open">open</Badge>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
