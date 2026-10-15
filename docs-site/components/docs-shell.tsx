"use client";

// Notebook shell adapted from rehearsal/docs/components/docs-shell.tsx.
import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { RootProvider } from "fumadocs-ui/provider/next";
import { DocsLayout } from "fumadocs-ui/layouts/notebook";
import { DocsPage, DocsBody } from "fumadocs-ui/layouts/notebook/page";
import type { Root } from "fumadocs-core/page-tree";
import type { TOCItemType } from "fumadocs-core/toc";
import dynamic from "next/dynamic";
import { DocsHeader } from "./site-header";
import { PageTools } from "./page-actions";
import { PARTS } from "@/app/pages";

const SearchDialog = dynamic(() => import("./search-dialog"), { ssr: false });
const tree: Root = {
  name: "Lighthouse Memory",
  children: PARTS.map(([name, pages]) => ({
    type: "folder",
    name,
    defaultOpen: true,
    collapsible: false,
    children: pages.map(([url, name]) => ({ type: "page", name, url })),
  })),
};
function NoSidebarFooter() {
  return null;
}
function PageFrame({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [toc, setToc] = useState<TOCItemType[]>([]);
  useEffect(() => {
    const timer = setTimeout(
      () =>
        setToc(
          [
            ...document.querySelectorAll(".lh-prose h2[id], .lh-prose h3[id]"),
          ].map((heading) => ({
            title: heading.textContent ?? "",
            url: `#${heading.id}`,
            depth: Number(heading.tagName.slice(1)),
          })),
        ),
      0,
    );
    return () => clearTimeout(timer);
  }, [path]);
  return (
    <DocsPage
      key={path}
      toc={toc}
      id="article"
      className="lh-page *:mx-auto *:w-full *:max-w-(--lh-column)"
      breadcrumb={{ enabled: false }}
      tableOfContent={{ style: "clerk" }}
      tableOfContentPopover={{ style: "clerk" }}
    >
      <PageTools />
      <DocsBody className="lh-prose">{children}</DocsBody>
      <div className="lh-article-footer">
        Lighthouse Memory · Built on FalkorDB
      </div>
    </DocsPage>
  );
}
export function DocsShell({ children }: { children: ReactNode }) {
  return (
    <RootProvider
      search={{ SearchDialog, preload: false }}
      theme={{
        defaultTheme: "light",
        enableSystem: true,
        hotKey: false,
        storageKey: "lighthouse-memory-theme",
      }}
    >
      <DocsLayout
        tree={tree}
        nav={{ mode: "top" }}
        tabs={false}
        slots={{ header: DocsHeader }}
        sidebar={{ collapsible: false, footer: NoSidebarFooter }}
        themeSwitch={{ enabled: false }}
        searchToggle={{ enabled: false }}
      >
        <PageFrame>{children}</PageFrame>
      </DocsLayout>
    </RootProvider>
  );
}
