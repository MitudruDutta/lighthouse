"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ChevronDown,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { Logo } from "./Logo";
import { WorkspaceName } from "./WorkspaceTools";

const KEY = "lighthouse.sidebar.collapsed";
const EVENT = "lighthouse-sidebar-change";
function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener(EVENT, listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener(EVENT, listener);
  };
}
function snapshot() {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}
function serverSnapshot() {
  return false;
}

export default function WorkspaceShell({
  navigation,
  children,
}: {
  navigation: ReactNode;
  children: ReactNode;
}) {
  const router = useRouter();
  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }
  const collapsed = useSyncExternalStore(subscribe, snapshot, serverSnapshot);
  function toggle() {
    try {
      window.localStorage.setItem(KEY, collapsed ? "0" : "1");
    } catch {
      return;
    }
    window.dispatchEvent(new Event(EVENT));
  }
  return (
    <div
      className="night console workspace-shell min-h-screen"
      data-collapsed={collapsed}
    >
      <a href="#workspace" className="skip-link">
        Skip to content
      </a>
      <aside className="side workspace-sidebar">
        <div className="workspace-brand">
          <Link href="/" aria-label="Lighthouse home">
            <Logo size={32} />
            <span className="workspace-brand-text">
              <strong>
                Lighthouse<span>.</span>
              </strong>
              <small>Maritime intelligence</small>
            </span>
          </Link>
        </div>
        <div className="workspace-desktop-nav">{navigation}</div>
        <details className="workspace-mobile-nav group">
          <summary>
            <WorkspaceName />
            <ChevronDown size={16} aria-hidden />
          </summary>
          <div>
            {navigation}
            <button className="sidebar-signout" onClick={signOut}>
              <LogOut size={17} />
              <span>Sign out</span>
            </button>
          </div>
        </details>
        <div className="workspace-sidebar-bottom">
          <button
            className="sidebar-collapse"
            onClick={toggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
          >
            {collapsed ? (
              <PanelLeftOpen size={18} />
            ) : (
              <PanelLeftClose size={18} />
            )}
            <span>{collapsed ? "Expand" : "Collapse sidebar"}</span>
          </button>
          <button
            className="sidebar-signout"
            aria-label="Sign out"
            onClick={signOut}
          >
            <LogOut size={17} />
            <span>Sign out</span>
          </button>
          <p>Evidence before action.</p>
        </div>
      </aside>
      <div className="workspace-body">{children}</div>
    </div>
  );
}
