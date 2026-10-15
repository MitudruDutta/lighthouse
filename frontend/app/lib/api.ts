import { notFound } from "next/navigation";

// The Lighthouse API, read from the server. LIGHTHOUSE_API names it; by default the one that
// `uv run uvicorn app.main:app --port 8100` serves on this machine.
const BASE = process.env.LIGHTHOUSE_API ?? "http://127.0.0.1:8100";

type Params = Record<string, string | number | boolean | undefined | null>;

/** One answer of the API. A 404 is the page's 404; any other failure is an error. */
export async function api<T>(path: string, params: Params = {}): Promise<T> {
  const url = new URL(path, BASE);
  for (const [name, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(name, String(value));
  }
  const response = await fetch(url);
  if (response.status === 404) notFound();
  if (!response.ok) throw new Error(`${path}: ${response.status} ${await response.text()}`);
  return response.json() as Promise<T>;
}

/** A path segment for an id that may hold "/" or ":", such as a berth key or an episode id. */
export function segments(id: string): string {
  return id.split("/").map(encodeURIComponent).join("/");
}

export type Ref = [string, string | number];

export type Status = {
  graph: string;
  counts: Record<string, number>;
  open_episodes: number;
  last_poll: Poll | null;
  last_world_poll: WorldPoll | null;
};
export type Poll = {
  at: string;
  feed_time: string | null;
  port_calls: Record<string, number>;
  watcher: Record<string, number>;
  reviewer: Record<string, Record<string, number>>;
  ms: number;
};
export type WorldPoll = { at: string; ports: number; days: string[]; rows: Record<string, number> };

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
