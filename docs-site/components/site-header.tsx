"use client";

// Three-zone header and sidebar trigger adapted from Rehearsal's docs header.
import { useEffect } from "react";
import Link from "next/link";
import { ArrowUpRight, Menu, Search } from "lucide-react";
import { useSearchContext } from "fumadocs-ui/contexts/search";
import { useNotebookLayout } from "fumadocs-ui/layouts/notebook";
import { ThemeToggle } from "./theme-toggle";
import { Mark } from "./mark";
const CONSOLE =
  process.env.NEXT_PUBLIC_MEMORY_CONSOLE_URL ?? "http://localhost:3003";
export function DocsHeader() {
  const { slots } = useNotebookLayout();
  const Trigger = slots.sidebar.trigger;
  const { setOpenSearch } = useSearchContext();
  useEffect(() => {
    function key(event: KeyboardEvent) {
      const el = event.target as HTMLElement | null;
      if (
        event.key !== "/" ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        (el &&
          (el.isContentEditable ||
            /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)))
      )
        return;
      event.preventDefault();
      setOpenSearch(true);
    }
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [setOpenSearch]);
  return (
    <header className="lh-header sticky top-(--fd-docs-row-1) col-span-full row-start-1 [contain:inline-size] layout:[--fd-header-height:--spacing(18)]">
      <div className="lh-header-inner">
        <Link href="/" className="lh-brand">
          <Mark />
          <span>
            Lighthouse <small>Memory docs</small>
          </span>
        </Link>
        <button
          className="lh-search"
          aria-keyshortcuts="Control+K Meta+K /"
          onClick={() => setOpenSearch(true)}
        >
          <Search size={18} />
          <span>Search documentation</span>
          <kbd>Ctrl K</kbd>
        </button>
        <div className="lh-header-actions">
          <button
            className="lh-mobile-search lh-icon"
            aria-label="Search documentation"
            onClick={() => setOpenSearch(true)}
          >
            <Search size={19} />
          </button>
          <ThemeToggle />
          <a
            className="lh-source"
            href="https://github.com/MitudruDutta/lighthouse/tree/main/lighthouse-memory"
          >
            Source <ArrowUpRight size={15} />
          </a>
          <a href={CONSOLE} className="lh-console-link">
            Open console <ArrowUpRight size={16} />
          </a>
          <Trigger
            className="lh-nav-trigger lh-icon"
            aria-label="Open navigation"
          >
            <Menu size={21} />
          </Trigger>
        </div>
      </div>
    </header>
  );
}
