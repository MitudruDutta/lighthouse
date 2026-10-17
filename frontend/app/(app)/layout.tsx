import { Waves } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { TopSearch } from "@/app/components/TopSearch";
import WorkspaceShell from "@/app/components/WorkspaceShell";
import { Nav, NavList } from "@/app/components/Nav";
import { Refresh, WorkspaceName } from "@/app/components/WorkspaceTools";
import { type Berth, type Status, maybe, desk } from "@/app/lib/api";
import { isFresh } from "@/app/lib/freshness";
import { operations, operationsToken } from "@/app/lib/operations-server";
import { redirect } from "next/navigation";
import { active, type Queue } from "@/app/lib/operations";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <WorkspaceShell
      navigation={
        <Suspense fallback={<NavList />}>
          <CountedNav />
        </Suspense>
      }
    >
      <Suspense fallback={null}>
        <AccountGate />
      </Suspense>
      <header className="workspace-header sticky top-0 z-20 border-b backdrop-blur-md">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3 px-5 py-3 md:px-8">
          <span className="hidden items-center gap-2 text-faint xl:flex">
            <Waves size={16} aria-hidden />
            <span className="text-xs">Workspace</span>
            <span className="px-1 text-faint">/</span>
            <WorkspaceName />
          </span>
          <TopSearch />
          <Refresh />
          <Suspense fallback={null}>
            <Live />
          </Suspense>
        </div>
      </header>
      <main
        id="workspace"
        className="mx-auto max-w-[1600px] px-5 py-7 md:px-8 md:py-9"
      >
        {children}
      </main>
      <footer className="mx-auto flex max-w-[1600px] flex-wrap justify-between gap-3 px-5 pt-4 pb-8 text-[10px] text-faint md:px-8">
        <span>
          Fintraffic / digitraffic.fi · CC BY 4.0 &nbsp; / &nbsp; Source: IMF
          PortWatch
        </span>
        <Link href="/sources" className="link">
          Source health & attribution ↗
        </Link>
      </footer>
    </WorkspaceShell>
  );
}

async function CountedNav() {
  const [status, queue, berths] = await Promise.all([
    maybe<Status>("/api/status"),
    operations<Queue>("cases"),
    maybe<Berth[]>("/api/berths"),
  ]);
  return (
    <Nav
      counts={{
        "/ports": status?.counts.Port,
        "/berths": berths?.filter((b) => b.overload).length,
        "/desk": queue?.cases.filter(active).length,
        "/episodes": status?.open_episodes,
        "/learned": status?.counts.Lesson,
      }}
    />
  );
}

async function Live() {
  const status = await maybe<Status>("/api/status");
  const fresh =
    status &&
    isFresh(status.last_poll?.at, status.now, 15) &&
    status.availability.feed;
  return (
    <Link
      href="/sources"
      className="hidden shrink-0 items-center gap-2 border-l border-[var(--edge)] pl-3 text-xs sm:flex"
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: fresh ? "var(--mint)" : "var(--coral)" }}
        aria-hidden
      />
      {fresh
        ? "Feed connected"
        : status
          ? "Feed delayed"
          : "Updates unavailable"}
    </Link>
  );
}

async function AccountGate() {
  const token = await operationsToken();
  if (!token || !token.startsWith("lhs_")) redirect("/login");
  const session = await desk("/api/auth/me", token);
  if (!session.ok && session.status === 401) redirect("/login");
  return null;
}
