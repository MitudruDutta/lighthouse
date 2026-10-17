import { NextRequest, NextResponse } from "next/server";

import { type Found, maybe, segments } from "@/app/lib/api";

const KINDS = new Set(["Vessel", "Port", "Berth"]);

function where(kind: string, key: string | number): string {
  if (kind === "Vessel") return `/vessels/${key}`;
  if (kind === "Port") return `/ports/${encodeURIComponent(String(key))}`;
  return `/berths/${segments(String(key))}`;
}

function shown(kind: string, item: Found, earlier: boolean) {
  const values = (item.state ?? (item as { values?: Record<string, unknown> }).values ?? {}) as Record<
    string,
    unknown
  >;
  return {
    href: where(kind, item.key),
    name: String(values.name ?? item.key),
    key: String(item.key),
    detail: [values.country, values.nationality, values.area].filter(Boolean).map(String).join(", "),
    earlier: earlier ? String(item.state?.valid_from ?? "") : undefined,
  };
}

/** The ships, ports, or berths whose name holds `q`, for the search box of
 * the workspace: names now first, then earlier names of what was renamed. The API's own
 * errors stay on the server; the box only learns that nothing could be read. */
export async function GET(request: NextRequest) {
  const q = (request.nextUrl.searchParams.get("q") ?? "").trim().slice(0, 200);
  const asked = request.nextUrl.searchParams.get("kind") ?? "Vessel";
  const kind = KINDS.has(asked) ? asked : "Vessel";
  if (!q) return NextResponse.json({ results: [] });
  const [now, before] = await Promise.all([
    maybe<Found[]>("/api/search", { q, kind, partial: true, limit: 8 }),
    maybe<Found[]>("/api/search", { q, kind, earlier: true, limit: 8 }),
  ]);
  if (now === null && before === null) return NextResponse.json({ results: [], unavailable: true });
  const results = (now ?? []).map((item) => shown(kind, item, false));
  const seen = new Set(results.map((item) => item.key));
  for (const item of before ?? []) {
    if (!seen.has(String(item.key)) && results.length < 10) {
      results.push(shown(kind, item, true));
      seen.add(String(item.key));
    }
  }
  return NextResponse.json({ results }, { headers: { "Cache-Control": "no-store" } });
}
