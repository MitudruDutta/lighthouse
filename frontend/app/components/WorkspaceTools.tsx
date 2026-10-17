"use client";

import { RefreshCw } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { Suspense, useEffect, useTransition } from "react";

const NAMES: Record<string, string> = {
  dashboard: "Needs attention", ports: "World ports", berths: "Berth board", episodes: "Event history",
  learned: "Lessons & playbooks", desk: "Case files", sources: "Data sources",
  vessels: "Vessel details", portcalls: "Port call details",
  agents: "Agent activity", investigate: "Evidence graph", cases: "Case investigation", profile: "Profile",
};

export function WorkspaceName() {
  return <Suspense fallback={<span className="text-sm">Workspace</span>}><PathName /></Suspense>;
}

function PathName() {
  const path = usePathname();
  return <span className="text-sm font-medium">{path === "/desk/chat" ? "Ask the desk" : NAMES[path.split("/")[1]] ?? "Workspace"}</span>;
}

export function Refresh() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") startTransition(() => router.refresh());
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [router]);
  return (
    <button type="button" className="refresh-button" onClick={() => startTransition(() => router.refresh())} disabled={pending} aria-label="Refresh workspace" title="Refresh now · updates automatically every minute">
      <RefreshCw size={15} className={pending ? "animate-spin" : ""} aria-hidden />
      <span className="hidden lg:inline">{pending ? "Refreshing…" : "Refresh"}</span>
    </button>
  );
}
