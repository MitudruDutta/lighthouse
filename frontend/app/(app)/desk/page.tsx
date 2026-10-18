import { Suspense } from "react";
import Link from "next/link";
import type { Metadata } from "next";
import CaseBoard from "@/app/components/operations/CaseBoard";
import { Card, Loading } from "@/app/components/ui";
import { maybe, type Status } from "@/app/lib/api";
import { type Queue } from "@/app/lib/operations";
import { operations } from "@/app/lib/operations-server";
export const metadata: Metadata = { title: "Case files" };
export default function CaseFiles() {
  return (
    <Suspense fallback={<Loading what="investigations" />}>
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
      <Card title="Your investigations">
        <p>Sign in to view your team’s cases.</p>
        <Link href="/login" className="ops-primary mt-4">
          Sign in →
        </Link>
      </Card>
    );
  return (
    <CaseBoard
      investigations
      queue={queue}
      now={status.now}
      globalDay={status.last_world_poll?.newest}
      feedAt={status.last_poll?.at}
      live={status.last_ais}
    />
  );
}
