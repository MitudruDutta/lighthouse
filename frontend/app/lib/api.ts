import { notFound } from "next/navigation";
import { cache } from "react";

// The Lighthouse API, read from the server. LIGHTHOUSE_API names it; by default the one that
// `uv run uvicorn app.main:app --port 8100` serves on this machine.
const BASE = process.env.LIGHTHOUSE_API ?? "http://127.0.0.1:8100";

type Params = Record<string, string | number | boolean | undefined | null>;

// Share one parsed response across panels in a server render, even with an abort signal.
const read = cache(async (url: string) => {
  const response = await fetch(url, { signal: AbortSignal.timeout(15_000) });
  return { status: response.status, ok: response.ok, data: response.ok ? await response.json() : null };
});

/** One answer of the API. A 404 is the page's 404; any other failure is an error. */
export async function api<T>(path: string, params: Params = {}): Promise<T> {
  const url = new URL(path, BASE);
  for (const [name, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(name, String(value));
  }
  const response = await read(url.toString());
  if (response.status === 404 && /^\/api\/(ports|berths|vessels|portcalls|episodes)\/.+/.test(path)) notFound();
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.data as T;
}

/** One answer of the API, or null when the API cannot be reached or refuses: for a page
 * that should say so in words instead of failing. */
export async function maybe<T>(path: string, params: Params = {}): Promise<T | null> {
  try {
    return await api<T>(path, params);
  } catch {
    return null;
  }
}

/** A path segment for an id that may hold "/" or ":", such as a berth key or an episode id. */
export function segments(id: string): string {
  return id.split("/").map(encodeURIComponent).join("/");
}

export type Ref = [string, string | number];

export type Status = {
  now: string;
  counts: Record<string, number>;
  open_episodes: number;
  last_poll: Poll | null;
  last_world_poll: WorldPoll | null;
  last_desk: DeskLook | null;
  availability: { feed: boolean; portwatch: boolean; desk: boolean };
};
export type DeskLook = { at: string; did: Record<string, number>; waiting: number };
export type Poll = {
  at: string;
  feed_time: string | null;
  port_calls: Record<string, number>;
};
export type WorldPoll = { at: string; ports: number; days: string[]; rows: Record<string, number>; newest?: string; state?: "running" | "updating" | "complete" };

// [key, name, iso3, country, lat, lon, calls]
export type WorldPort = [string, string | null, string | null, string | null, number, number, number | null];
export type World = { newest_day: string | null; ports: WorldPort[]; unusual: Record<string, string> };

export type PortRow = {
  key: string;
  name?: string;
  country?: string;
  iso3?: string;
  continent?: string;
  calls?: number;
  calls_container?: number;
  calls_dry_bulk?: number;
  calls_general_cargo?: number;
  calls_roro?: number;
  calls_tanker?: number;
  import_tonnes?: number;
  export_tonnes?: number;
  valid_from?: string;
};
export type Day = Omit<PortRow, "key" | "name" | "country" | "iso3" | "continent"> & { day: string };
export type Port = {
  key: string;
  place: { name?: string; country?: string; iso3?: string; continent?: string; lat?: number; lon?: number };
  days: Day[];
  lessons: Lesson[];
  episodes: EpisodeSummary[];
  port_calls: Record<string, number[]>;
};

export type Overload = { from: string; until: string | null; most: number; calls: number[] };
export type Berth = {
  berth: string;
  name: string | null;
  area: string | null;
  capacity: number;
  together: number[];
  overload: Overload | null;
};

export type Entry = {
  id: string;
  seq: number;
  type: string;
  at: string;
  by: string;
  cites: Ref[];
  [value: string]: unknown;
};
export type EpisodeSummary = {
  id: string;
  by: string;
  opened_at: string;
  closed_at?: string;
  entry_count: number;
  about?: Ref[];
  outcome?: Record<string, unknown> | null;
  first?: Entry | null;
};
export type Episode = EpisodeSummary & { about: Ref[]; entries: Entry[] };

export type Lesson = {
  id: string;
  statement: string;
  weight: number;
  supported_by?: string[];
  contradicted_by?: string[];
  about?: Ref[];
  touched_at?: string;
};
export type Playbook = {
  id: string;
  name: string;
  version: number;
  enabled: boolean;
  trigger: Record<string, unknown>;
  steps: Record<string, unknown>[];
  runs?: number;
  succeeded?: number;
  failed?: number;
  supported_by: string[];
};

export type PortCall = {
  key: number;
  at: string;
  values: Record<string, unknown> | null;
  relations: Record<string, (string | number)[]>;
  versions: Record<string, unknown>[];
  episodes: EpisodeSummary[];
};

export type Handoff = {
  id: string;
  by: string;
  ask?: string;
  at: string;
  accepted_at?: string;
  points_to: Ref[];
};
export type Assessment = {
  episode: string;
  id: string;
  at: string;
  by: string;
  text: string;
} & Checked;
/** How an answer of the Desk was found: the tools, with the rows each returned and how long
 * it took, and whether what it says rests on what they showed. */
export type Checked = {
  model?: string;
  outcome?: "grounded" | "not in the graph" | "unsupported";
  unsupported?: string[];
  tools?: string[];
  tool_rows?: number[];
  tool_ms?: number[];
};
export type DeskInbox = { waiting_count: number; waiting: Handoff[]; assessed: Assessment[] };

export type Message = {
  seq: number;
  role: string;
  text: string;
  at: string;
  by: string;
  mentions: Ref[];
} & Checked;
export type Session = { id: string; opened_at: string; active_at?: string; messages: number };
export type Answer = { session: string; seq: number; text: string; tools: string[]; mentions: Ref[] };
export type ModelChoice = { id: string; provider: string; model: string };

export type Vessel = { key: number; versions: Record<string, unknown>[]; port_calls: number[] };
export type BerthPage = {
  key: string;
  versions: Record<string, unknown>[];
  port_calls: number[];
  lessons: Lesson[];
  episodes: EpisodeSummary[];
};
export type Found = { key: string | number; score: number; name?: string; state?: Record<string, unknown> };

/** The cookie that holds the desk token of the person signed in. */
export const DESK_COOKIE = "lighthouse_desk";

/** A request to the desk routes, signed with the token of the person signed in. Gives the
 * answer, or only the status when it is not 200: what went wrong is for the log of the API,
 * never for the page. */
export async function desk<T>(
  path: string,
  token: string,
  body?: unknown,
  method: "POST" | "PUT" = "POST",
): Promise<{ ok: true; data: T } | { ok: false; status: number }> {
  try {
    const response = await fetch(new URL(path, BASE), {
      method: body === undefined ? "GET" : method,
      headers: { Authorization: `Bearer ${token}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(body === undefined ? 15_000 : 180_000),
      cache: "no-store",
    });
    return response.ok ? { ok: true, data: (await response.json()) as T } : { ok: false, status: response.status };
  } catch {
    return { ok: false, status: 503 };
  }
}

export type Activity = {
  entries: (Entry & { episode: string })[];
  opened: { day: string; count: number }[];
};
export type Unusual = {
  port: string;
  name: string | null;
  state: string;
  calls: number;
  usual: number;
  since: string;
  episode: string;
};

export type GraphNode = { id: number; ref: Ref; title: string; state: string | null; by?: string | null; at?: string | null; description?: string };
export type GraphEdge = { id: number; source: number; target: number; type: string; since: string | null };
export type Network = { focus: number | null; nodes: GraphNode[]; edges: GraphEdge[]; limited: boolean };
export type Intelligence = { tasks: Record<string, number>; handoffs: { total: number; accepted: number }; assessments: { total: number; grounded: number }; groups: { size: number; members: Ref[] }[]; central: { entity: Ref; score: number; name: string }[] };
export type Quality = { ports: { total: number; located: number; daily_counts: number; joined_by_locode: number }; calls: { total: number; berths: number; with_berth: number; with_eta: number; with_actual_arrival: number; multiple_areas: number }; versions: number };
export type ConnectionStep = { from: Ref; to: Ref; relation: string; forward: boolean; current: boolean; since: string | null; until: string | null };
