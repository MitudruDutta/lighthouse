"use client";

import Link from "next/link";
import { useState } from "react";
import index from "@/app/search-index.json";
import { rank } from "./search-rank";
import {
  SearchDialog,
  SearchDialogClose,
  SearchDialogContent,
  SearchDialogFooter,
  SearchDialogHeader,
  SearchDialogIcon,
  SearchDialogInput,
  SearchDialogList,
  SearchDialogOverlay,
  type SharedProps,
} from "fumadocs-ui/components/dialog/search";

/** Shown before the reader types, and offered again when a search finds nothing. */
const START: [string, string][] = [
  ["Python quickstart", "/library"],
  ["Memory HTTP API", "/memory-api"],
  ["Versioned memory", "/history"],
  ["Models and agent integration", "/integrations"],
];

function NoResults() {
  return (
    <div className="px-4 py-6 text-sm">
      <p className="font-medium text-foreground">No page matches that.</p>
      <p className="mt-1 text-muted-foreground">
        If you pasted an error message, try a shorter part of it. These pages
        answer most questions:
      </p>
      <ul className="mt-3 grid gap-1">
        {START.map(([name, href]) => (
          <li key={href}>
            <Link
              href={href}
              className="text-link underline-offset-2 hover:underline"
            >
              {name}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Search dialog adapted from Rehearsal; Lighthouse’s static memory index loads with this lazy component.
 */
export default function StaticSearchDialog(props: SharedProps) {
  const [query, setQuery] = useState("");
  const found = rank(index, query).map((page) => ({
      type: "page" as const,
      id: page.path,
      url: page.path,
      content: page.title,
    }));
  return (
    <SearchDialog search={query} onSearchChange={setQuery} {...props}>
      <SearchDialogOverlay />
      <SearchDialogContent>
        <SearchDialogHeader>
          <SearchDialogIcon />
          <SearchDialogInput placeholder="Search memory, graph queries, API…" />
          <SearchDialogClose />
        </SearchDialogHeader>
        <SearchDialogList
          items={query.trim() ? found : undefined}
          defaultItems={START.map(([name, url]) => ({
            type: "page" as const,
            id: url,
            content: name,
            url,
          }))}
          Empty={NoResults}
        />
        <SearchDialogFooter className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>
            <kbd className="rounded border px-1 font-mono">↑</kbd>{" "}
            <kbd className="rounded border px-1 font-mono">↓</kbd> to move
          </span>
          <span>
            <kbd className="rounded border px-1 font-mono">Enter</kbd> to open
          </span>
          <span>
            <kbd className="rounded border px-1 font-mono">Esc</kbd> to close
          </span>
        </SearchDialogFooter>
      </SearchDialogContent>
    </SearchDialog>
  );
}
