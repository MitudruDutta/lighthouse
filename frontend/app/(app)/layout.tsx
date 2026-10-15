import { ChevronDown, Search, Waves } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { Logo } from "@/app/components/Logo";
import { Nav, NavList } from "@/app/components/Nav";
import { Refresh, WorkspaceName } from "@/app/components/WorkspaceTools";
import { ago } from "@/app/components/ui";
import { type Berth, type DeskInbox, type Status, maybe } from "@/app/lib/api";
import { isFresh, utcTime } from "@/app/lib/freshness";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="night console min-h-screen lg:grid lg:grid-cols-[232px_minmax(0,1fr)]">
      <a href="#workspace" className="skip-link">Skip to content</a>
      <aside className="side flex flex-col gap-7 border-b px-4 py-5 lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto lg:border-r lg:border-b-0 lg:py-7">
        <div className="flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 px-2">
            <Logo size={32} />
            <span><span className="display block text-xl">Lighthouse<span style={{ color: "#ddf78a" }}>.</span></span><span className="mt-0.5 block text-[10px] uppercase tracking-[0.18em] text-faint">Maritime intelligence</span></span>
          </Link>
          <span className="text-xs text-faint lg:hidden">Workspace</span>
        </div>
        <div className="hidden lg:block"><Suspense fallback={<NavList />}><CountedNav /></Suspense></div>
        <details className="group lg:hidden">
          <summary className="flex cursor-pointer list-none items-center justify-between rounded-md border border-[var(--edge-2)] px-3 py-2 text-sm">
            <WorkspaceName /><ChevronDown size={16} className="group-open:rotate-180" aria-hidden />
          </summary>
          <div className="pt-5"><Suspense fallback={<NavList />}><CountedNav /></Suspense></div>
        </details>
        <div className="mt-auto hidden pt-4 lg:block"><Suspense fallback={null}><AtWork /></Suspense></div>
        <p className="hidden px-2 text-[10px] text-faint lg:block">Connected by memory. Built on FalkorDB.</p>
      </aside>
      <div className="min-w-0">
        <header className="workspace-header sticky top-0 z-20 border-b backdrop-blur-md">
          <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3 px-5 py-3 md:px-8">
            <span className="hidden items-center gap-2 text-faint xl:flex"><Waves size={16} aria-hidden /><span className="text-xs">Workspace</span><span className="px-1 text-faint">/</span><WorkspaceName /></span>
            <form action="/search" role="search" className="flex min-w-0 flex-1 gap-2 xl:ml-auto xl:max-w-md">
              <label className="workspace-search min-w-0 flex-1"><Search size={15} aria-hidden /><input name="q" placeholder="Search by name…" aria-label="Search ships, ports or berths" /></label>
              <select name="kind" aria-label="Search category" className="!w-23 !px-2 !text-xs"><option value="Vessel">Ships</option><option value="Port">Ports</option><option value="Berth">Berths</option></select>
            </form>
            <Refresh />
            <Suspense fallback={null}><Live /></Suspense>
          </div>
        </header>
        <main id="workspace" className="mx-auto max-w-[1600px] px-5 py-7 md:px-8 md:py-9">{children}</main>
        <footer className="mx-auto flex max-w-[1600px] flex-wrap justify-between gap-3 px-5 pt-4 pb-8 text-[10px] text-faint md:px-8">
          <span>Fintraffic / digitraffic.fi · CC BY 4.0 &nbsp; / &nbsp; Source: IMF PortWatch</span>
          <Link href="/sources" className="link">Source health & attribution ↗</Link>
        </footer>
      </div>
    </div>
  );
}

async function CountedNav() {
  const [status, inbox, berths] = await Promise.all([maybe<Status>("/api/status"), maybe<DeskInbox>("/api/desk", { limit: 1 }), maybe<Berth[]>("/api/berths")]);
  return <Nav counts={{ "/ports": status?.counts.Port, "/berths": berths?.filter((b) => b.overload).length, "/desk": inbox?.waiting_count, "/episodes": status?.open_episodes, "/learned": status?.counts.Lesson }} />;
}

async function Live() {
  const status = await maybe<Status>("/api/status");
  const fresh = status && isFresh(status.last_poll?.at, status.now, 15) && status.availability.feed;
  return (
    <Link href="/sources" className="hidden shrink-0 items-center gap-2 border-l border-[var(--edge)] pl-3 text-xs sm:flex">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: fresh ? "var(--mint)" : "var(--coral)" }} aria-hidden />
      {fresh ? "Feed connected" : status ? "Feed delayed" : "Updates unavailable"}
    </Link>
  );
}

function Agent({ active, name, does }: { active: boolean; name: string; does: string }) {
  return <li className="flex items-start gap-2.5"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: active ? "var(--mint)" : "var(--beam)" }} aria-hidden /><span><span className="block text-xs font-medium">{name}</span><span className="mt-0.5 block text-[10px] leading-relaxed text-faint">{does}</span></span></li>;
}

async function AtWork() {
  const status = await maybe<Status>("/api/status");
  if (!status) return <p className="px-2 text-xs text-faint">Updates temporarily unavailable.</p>;
  const now = utcTime(status.now);
  const fresh = isFresh(status.last_poll?.at, status.now, 15) && status.availability.feed;
  const worldFresh = isFresh(status.last_world_poll?.at, status.now, 90) && status.availability.portwatch;
  const deskFresh = status.availability.desk && isFresh(status.last_desk?.at, status.now, 5);
  return (
    <section aria-label="Agent status" className="border-t pt-5" style={{ borderColor: "var(--edge)" }}>
      <h2 className="mb-4 px-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-faint">Agent status</h2>
      <ul className="grid gap-3 px-2">
        <Agent active={fresh} name="Watcher" does={status.last_poll ? `Berths checked ${ago(status.last_poll.at, now)}` : "Awaiting first import"} />
        <Agent active={worldFresh} name="Port Watcher" does={status.last_world_poll ? `Source checked ${ago(status.last_world_poll.at, now)}` : "Awaiting first import"} />
        <Agent active={fresh} name="Reviewer" does={fresh ? "Reviews completed episodes" : "Waiting for feed"} />
        <Agent active={Boolean(deskFresh)} name="Desk agent" does={!status.availability.desk ? "Temporarily unavailable" : deskFresh ? "Ready for investigations" : "Awaiting next run"} />
      </ul>
    </section>
  );
}
