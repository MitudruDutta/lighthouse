"use client";

import { docs } from "@/app/lib/links";

import {
  BookOpenCheck,
  BookOpen,
  Database,
  Bot,
  Network,
  Globe2,
  History,
  Inbox,
  LayoutDashboard,
  type LucideIcon,
  MessagesSquare,
  Search,
  Ship,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export type Counts = Partial<Record<string, number>>;

const GROUPS: [string, [string, string, LucideIcon][]][] = [
  [
    "Operations",
    [
      ["/dashboard", "Overview", LayoutDashboard],
      ["/ports", "Global ports", Globe2],
      ["/berths", "Berth board", Ship],
      ["/search", "Search memory", Search],
    ],
  ],
  [
    "Intelligence",
    [
      ["/agents", "Agent control room", Bot],
      ["/investigate", "Investigate", Network],
      ["/desk", "Desk inbox", Inbox],
      ["/desk/chat", "Ask the desk", MessagesSquare],
      ["/episodes", "Episodes", History],
      ["/learned", "Lessons & playbooks", BookOpenCheck],
    ],
  ],
  ["Workspace", [["/sources", "Data sources", Database], [docs(), "Documentation", BookOpen]]],
];

function current(path: string): string | undefined {
  // The longest link that the path starts with is the current page.
  return GROUPS.flatMap(([, links]) => links.map(([to]) => to))
    .filter((to) => path === to || path.startsWith(`${to}/`))
    .sort((a, b) => b.length - a.length)[0];
}

/** The pages, in two groups, with a count beside those that have one. */
export function NavList({ at, counts = {} }: { at?: string; counts?: Counts }) {
  return (
    <nav aria-label="Workspace pages" className="grid gap-6">
      {GROUPS.map(([group, links]) => (
        <div key={group} className="grid gap-1">
          <h2 className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-faint">{group}</h2>
          {links.map(([to, label, Icon]) => (
            <Link key={to} href={to} className="nav-link shrink-0 text-sm" aria-current={to === at ? "page" : undefined}>
              <Icon size={16} strokeWidth={1.8} aria-hidden />
              <span className="flex-1">{label}</span>
              {counts[to] ? (
                <span className="tabular rounded-md px-1.5 text-[11px]" style={{ background: "var(--rule-soft)", color: "var(--ink-2)" }}>
                  {counts[to]!.toLocaleString("en")}
                </span>
              ) : null}
            </Link>
          ))}
        </div>
      ))}
    </nav>
  );
}

export function Nav({ counts }: { counts?: Counts }) {
  return <NavList at={current(usePathname())} counts={counts} />;
}
