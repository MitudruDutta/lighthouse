"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type Result = { href: string; name: string; key: string; detail: string; earlier?: string };

/** The workspace's search box: results appear under it as you type. */
export function TopSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("Vessel");
  const [results, setResults] = useState<Result[] | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const words = q.trim();
    if (!words) return;
    const stop = new AbortController();
    const wait = setTimeout(async () => {
      try {
        const response = await fetch(`/api/search?${new URLSearchParams({ q: words, kind })}`, {
          signal: stop.signal,
        });
        const data = await response.json();
        setResults(data.results ?? []);
        setUnavailable(!!data.unavailable);
        setActive(-1);
      } catch {
        if (!stop.signal.aborted) setUnavailable(true);
      }
    }, 220);
    return () => {
      clearTimeout(wait);
      stop.abort();
    };
  }, [q, kind]);

  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  const shown = q.trim() ? results : null;
  const label = kind === "Vessel" ? "ships" : kind === "Port" ? "ports" : "berths";
  return (
    <div className="top-search min-w-0 flex-1 xl:ml-auto xl:max-w-md" ref={box} role="search">
      <label className="workspace-search min-w-0 flex-1">
        <Search size={15} aria-hidden />
        <input
          value={q}
          onChange={(event) => {
            setQ(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            const count = shown?.length ?? 0;
            if (event.key === "ArrowDown" && count) {
              event.preventDefault();
              setActive((n) => (n + 1) % count);
            } else if (event.key === "ArrowUp" && count) {
              event.preventDefault();
              setActive((n) => (n <= 0 ? count - 1 : n - 1));
            } else if (event.key === "Enter" && shown?.length) {
              event.preventDefault();
              router.push(shown[Math.max(active, 0)].href);
              setOpen(false);
            } else if (event.key === "Escape") setOpen(false);
          }}
          placeholder={`Find ${label} by name…`}
          aria-label="Find ships, ports or berths by name"
          role="combobox"
          aria-expanded={open && !!shown}
          aria-controls="top-search-results"
          aria-autocomplete="list"
          autoComplete="off"
        />
      </label>
      <select
        value={kind}
        onChange={(event) => setKind(event.target.value)}
        aria-label="Search category"
        className="!w-23 !px-2 !text-xs"
      >
        <option value="Vessel">Ships</option>
        <option value="Port">Ports</option>
        <option value="Berth">Berths</option>
      </select>
      {open && shown ? (
        <div className="top-search-results" id="top-search-results" role="listbox" aria-label="Results">
          {shown.length ? (
            shown.map((item, n) => (
              <Link
                key={`${item.key}-${n}`}
                href={item.href}
                role="option"
                aria-selected={n === active}
                onClick={() => setOpen(false)}
              >
                <span>
                  <strong>{item.name}</strong>
                  <small>{item.key}</small>
                </span>
                <em>{item.earlier ? "Earlier name" : item.detail}</em>
              </Link>
            ))
          ) : (
            <p>{unavailable ? "Search is unavailable just now." : `No ${label} have that name. Try one word of it.`}</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
