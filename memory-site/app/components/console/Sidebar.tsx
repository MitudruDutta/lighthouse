"use client";
import Link from "next/link";
import {
  Activity,
  Bot,
  Check,
  ChevronsUpDown,
  CreditCard,
  Database,
  Folder,
  KeyRound,
  LayoutDashboard,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Settings,
} from "lucide-react";
import { Mark } from "../Brand";
import type { Overview } from "../../lib/types";
import { ThemeMenu } from "./ThemeSwitch";
import { useMenu } from "./ui";

export const SECTIONS: { label: string; items: [string, string, typeof Folder][] }[] = [
  {
    label: "Project",
    items: [
      ["overview", "Overview", LayoutDashboard],
      ["memory", "Memory explorer", Database],
      ["agents", "Agents & MCP", Bot],
      ["keys", "API keys", KeyRound],
      ["usage", "Usage", Activity],
    ],
  },
  {
    label: "Workspace",
    items: [
      ["projects", "Projects", Folder],
      ["plan", "Plan & billing", CreditCard],
      ["settings", "Settings", Settings],
    ],
  },
];

export function Sidebar({
  user,
  workspaces,
  workspace,
  view,
  counts,
  collapsed,
  open,
  href,
  toggle,
  close,
  switchTo,
  newWorkspace,
  signOut,
}: {
  user: Overview["user"];
  workspaces: Overview["workspaces"];
  workspace?: Overview["workspaces"][number];
  view: string;
  counts: Record<string, number>;
  collapsed: boolean;
  open: boolean;
  href: (section: string, extra?: Record<string, string>) => string;
  toggle: () => void;
  close: () => void;
  switchTo: (id: string) => void;
  newWorkspace: () => void;
  signOut: () => void;
}) {
  const [menuOpen, setMenuOpen, menuRef] = useMenu();
  const initial = (workspace?.name ?? user.name)[0]?.toUpperCase();
  return (
    <aside
      className="cx-sidebar"
      data-collapsed={collapsed || undefined}
      data-open={open || undefined}
    >
      <div className="cx-sidebar-head">
        <Link href="/dashboard" className="cx-logo" aria-label="Lighthouse Memory console">
          <Mark size={24} />
          <span>
            Lighthouse <b>Memory</b>
          </span>
        </Link>
        <button
          type="button"
          className="cx-icon cx-collapse"
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
        </button>
      </div>

      <div className="cx-switcher" ref={menuRef}>
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(!menuOpen)}
          title={collapsed ? workspace?.name : undefined}
        >
          <span className="cx-avatar">{initial}</span>
          <span className="cx-switcher-name">
            <strong>{workspace?.name ?? "Workspace"}</strong>
            <small>
              {workspaces.length > 1 ? `${workspaces.length} workspaces` : "Personal workspace"}
            </small>
          </span>
          <ChevronsUpDown size={14} />
        </button>
        {menuOpen ? (
          <div className="cx-menu" role="menu" aria-label="Workspaces">
            <p>Workspaces</p>
            {workspaces.map((item) => (
              <button
                key={item.id}
                type="button"
                role="menuitemradio"
                aria-checked={item.id === workspace?.id}
                onClick={() => {
                  setMenuOpen(false);
                  switchTo(item.id);
                }}
              >
                <span className="cx-avatar cx-avatar-small">{item.name[0]?.toUpperCase()}</span>
                <span>{item.name}</span>
                {item.id === workspace?.id ? <Check size={14} /> : null}
              </button>
            ))}
            <hr />
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMenuOpen(false);
                newWorkspace();
              }}
            >
              <Plus size={14} />
              New workspace
            </button>
            <Link
              role="menuitem"
              href={href("settings", { tab: "workspace" })}
              onClick={() => {
                setMenuOpen(false);
                close();
              }}
            >
              <Settings size={14} />
              Workspace settings
            </Link>
          </div>
        ) : null}
      </div>

      <nav aria-label="Console">
        {SECTIONS.map((section) => (
          <div key={section.label} className="cx-nav-group">
            <p>{section.label}</p>
            {section.items.map(([id, name, Icon]) => (
              <Link
                key={id}
                href={href(id)}
                aria-current={view === id ? "page" : undefined}
                onClick={close}
                title={collapsed ? name : undefined}
              >
                <Icon size={17} />
                <span>{name}</span>
                {counts[id] !== undefined ? <small>{counts[id]}</small> : null}
              </Link>
            ))}
          </div>
        ))}
      </nav>

      <ThemeMenu className="cx-theme" label up />
      <div className="cx-profile">
        <span className="cx-avatar cx-avatar-round">{user.name[0]?.toUpperCase()}</span>
        <span className="cx-profile-name">
          <strong>{user.name}</strong>
          <small>{user.email}</small>
        </span>
        <button
          type="button"
          className="cx-icon"
          aria-label="Sign out"
          title="Sign out"
          onClick={signOut}
        >
          <LogOut size={15} />
        </button>
      </div>
    </aside>
  );
}
