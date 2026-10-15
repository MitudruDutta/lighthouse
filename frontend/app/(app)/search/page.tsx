import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Card, Empty, Loading, Title, When } from "@/app/components/ui";
import { type Found, api, segments } from "@/app/lib/api";

export const metadata: Metadata = { title: "Find a ship or port" };

const KINDS: [string, string][] = [
  ["Vessel", "Ships"],
  ["Port", "Ports"],
  ["Berth", "Berths"],
];

export default function SearchPage(props: PageProps<"/search">) {
  return (
    <div className="grid gap-6">
      <Title lead="By a word of its name. A ship that was renamed is found by its old name too, when you ask for earlier names.">
        Find a ship, a port, or a berth
      </Title>
      <Suspense fallback={<Loading what="the search" />}>
        <Body {...props} />
      </Suspense>
    </div>
  );
}

function where(kind: string, key: string | number): string {
  if (kind === "Vessel") return `/vessels/${key}`;
  if (kind === "Port") return `/ports/${encodeURIComponent(String(key))}`;
  return `/berths/${segments(String(key))}`;
}

async function Body({ searchParams }: PageProps<"/search">) {
  const asked = await searchParams;
  const q = typeof asked.q === "string" ? asked.q.slice(0, 200) : "";
  const kind = typeof asked.kind === "string" && KINDS.some(([k]) => k === asked.kind) ? asked.kind : "Vessel";
  const earlier = asked.earlier === "1";
  const found = q.trim() ? await api<Found[]>("/api/search", { q, kind, earlier, limit: 30 }) : null;
  return (
    <>
      <form className="flex flex-wrap items-end gap-3" role="search">
        <label className="grid gap-1 text-sm">
          <span className="text-muted">Name</span>
          <input name="q" defaultValue={q} placeholder="Nordic, Helsinki, Mumbai…" className="w-72" autoFocus />
        </label>
        <label className="grid gap-1 text-sm">
          <span className="text-muted">Looking for</span>
          <select name="kind" defaultValue={kind}>
            {KINDS.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 pb-1.5 text-sm">
          <input type="checkbox" name="earlier" value="1" defaultChecked={earlier} />
          Earlier names too
        </label>
        <button type="submit">Find</button>
      </form>
      {found === null ? null : (
        <Card title={`${found.length} found`}>
          {found.length === 0 ? (
            <Empty>Nothing has that name. Try one word of it, or earlier names.</Empty>
          ) : (
            <ul className="grid gap-0">
              {found.map((item, n) => {
                const values = (item.state ?? (item as { values?: Record<string, unknown> }).values ?? {}) as Record<string, unknown>;
                return (
                  <li key={`${item.key}-${n}`} className="flex flex-wrap items-baseline justify-between gap-2 border-b py-2.5 text-sm last:border-b-0" style={{ borderColor: "var(--rule-soft)" }}>
                    <span>
                      <Link href={where(kind, item.key)} className="link font-medium">
                        {String(values.name ?? item.key)}
                      </Link>
                      <span className="ml-2 text-xs text-faint">{String(item.key)}</span>
                    </span>
                    <span className="text-xs text-muted">
                      {[values.country, values.nationality, values.area].filter(Boolean).map(String).join(", ")}
                      {item.state ? (
                        <>
                          {" "}
                          named so from <When at={String(item.state.valid_from)} day />
                        </>
                      ) : null}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      )}
    </>
  );
}
