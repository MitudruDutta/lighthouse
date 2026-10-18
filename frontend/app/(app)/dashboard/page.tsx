import { Suspense } from "react";
import Link from "next/link";
import type { Metadata } from "next";
import CaseBoard from "@/app/components/operations/CaseBoard";
import { Loading, Card } from "@/app/components/ui";
import { type Status, maybe } from "@/app/lib/api";
import { type Queue } from "@/app/lib/operations";
import { operations } from "@/app/lib/operations-server";
export const metadata: Metadata = { title: "Needs attention" };
export default function Dashboard() {
  return (
    <Suspense fallback={<Loading what="your attention queue" />}>
      <Body />
    </Suspense>
  );
}
async function Body() {
  const [queue, status] = await Promise.all([
    operations<Queue>("cases"),
    maybe<Status>("/api/status"),
  ]);
  if (!queue || !status)
    return (
      <Card title="Your operations workspace">
        <p>Sign in to see your cases, watchlist, and decisions.</p>
        <Link href="/login" className="ops-primary mt-4">
          Open your workspace →
        </Link>
      </Card>
    );
  return (
    <CaseBoard
      queue={queue}
      now={status.now}
      globalDay={status.last_world_poll?.newest}
      feedAt={status.last_poll?.at}
      live={status.last_ais}
    />
  );
}
