import Link from "next/link";
import { Suspense } from "react";

import type { Metadata } from "next";

import { Badge, Card, Empty, Loading, Prose, RefLink, Title, Trace, When, number } from "@/app/components/ui";
import { type DeskInbox, api, segments } from "@/app/lib/api";

export const metadata: Metadata = { title: "The desk" };

export default function DeskPage() {
  return (
    <div className="grid gap-5">
      <Title
        lead="The Watchers hand what they see to the desk. The Desk agent takes each one, looks further with the tools it picks, and writes down what it concludes, with the tools it used and what they read."
        aside={
          <Link href="/desk/chat" className="button-quiet">
            Ask the desk
          </Link>
        }
      >
        The desk
      </Title>
      <Suspense fallback={<Loading what="the desk" />}>
        <Inbox />
      </Suspense>
    </div>
  );
}

async function Inbox() {
  const inbox = await api<DeskInbox>("/api/desk", { limit: 30 });
  return (
    <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
      <Card title="Concluded by the Desk" aside={`${inbox.assessed.length} latest`}>
        {inbox.assessed.length === 0 ? (
          <Empty>The Desk agent has not concluded anything yet. Its conclusions appear here as it works through what waits.</Empty>
        ) : (
          <ol className="grid gap-5">
            {inbox.assessed.map((a) => (
              <li key={a.id} className="border-l-2 pl-4" style={{ borderColor: "var(--line)" }}>
                <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
                  <Badge tone="assessment">assessment</Badge>
                  <Link href={`/episodes/${segments(a.episode)}`} className="link break-all">
                    {a.episode}
                  </Link>
                  <span className="text-faint">
                    <When at={a.at} />
                  </span>
                </div>
                <Prose text={a.text} />
                <Trace found={a} />
              </li>
            ))}
          </ol>
        )}
      </Card>
      <Card title="Waiting for the desk" aside={`${number(inbox.waiting_count)} in all`}>
        {inbox.waiting.length === 0 ? (
          <Empty>Nothing waits.</Empty>
        ) : (
          <ul className="grid gap-3 text-sm">
            {inbox.waiting.map((h) => (
              <li key={h.id}>
                <div>{h.ask ?? "An episode to look into."}</div>
                <div className="mt-1 flex flex-wrap gap-2 text-xs text-faint">
                  from {h.by} · <When at={h.at} />
                  {h.points_to.slice(0, 2).map((r) => (
                    <RefLink key={`${r[0]}${r[1]}`} refer={r}>
                      episode
                    </RefLink>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
