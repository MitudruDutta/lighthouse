import Link from "next/link";
import type { ReactNode } from "react";

import { type Checked, type Entry, type Ref, segments } from "../lib/api";
import { describeTool } from "./words";

/** A time as the API gives it (UTC), in a short readable form. */
export function When({ at, day }: { at?: string | null; day?: boolean }) {
  if (!at) return <span className="text-faint">—</span>;
  // A time without a zone is UTC, as the library keeps every time.
  const utc = /T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(at) ? `${at}Z` : at;
  const text = new Date(utc).toISOString().replace("T", " ");
  return <time dateTime={at}>{day ? text.slice(0, 10) : `${text.slice(0, 16)} UTC`}</time>;
}

/** Where a reference leads: a port, a berth, a port call, an episode, or a lesson. */
export function href([label, key]: Ref): string | null {
  const id = String(key);
  switch (label) {
    case "Port":
      return `/ports/${encodeURIComponent(id)}`;
    case "PortCall":
      return `/portcalls/${encodeURIComponent(id)}`;
    case "Berth":
      return `/berths/${segments(id)}`;
    case "Vessel":
      return `/vessels/${encodeURIComponent(id)}`;
    case "Episode":
      return `/episodes/${segments(id)}`;
    case "Lesson":
      return `/learned#${encodeURIComponent(id)}`;
    default:
      return null;
  }
}

export function RefLink({ refer, children }: { refer: Ref; children?: ReactNode }) {
  const to = href(refer);
  const text = children ?? (
    <>
      <span className="text-faint">{refer[0]}</span> {String(refer[1])}
    </>
  );
  return to ? (
    <Link href={to} className="link">
      {text}
    </Link>
  ) : (
    <span>{text}</span>
  );
}

export function Card({ title, children, aside }: { title?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="card">
      {title ? (
        <header className="card-heading mb-3">
          <h2 className="min-w-0 text-[15px] leading-snug font-semibold">{title}</h2>
          {aside ? <div className="card-meta text-xs text-faint">{aside}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="card">
      <div className="text-sm text-muted">{label}</div>
      <div className="serif mt-1 text-3xl tabular-nums">{value}</div>
      {note ? <div className="mt-1 text-xs text-faint">{note}</div> : null}
    </div>
  );
}

const TONES: Record<string, string> = {
  quiet: "badge-warn",
  busy: "badge-hot",
  open: "badge-hot",
  closed: "badge-calm",
  observation: "badge-info",
  recall: "badge-learn",
  action: "badge-act",
  outcome: "badge-calm",
  assessment: "badge-learn",
};

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${TONES[tone ?? String(children)] ?? ""}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-faint">{children}</p>;
}

export function Loading({ what }: { what: string }) {
  return (
    <p className="py-10 text-center text-sm text-faint" role="status">
      Reading {what}…
    </p>
  );
}

export function number(value: unknown, digits = 0): string {
  return typeof value === "number" ? value.toLocaleString("en", { maximumFractionDigits: digits }) : "—";
}

/** What an episode is about, in words, from its first entry; its id when that says nothing. */
export function headline(id: string, first?: Entry | null): string {
  if (first?.situation === "port-activity") {
    return `${String(first.name ?? first.port)}: ${String(first.state)}, ${number(first.calls)} port calls against the usual ${number(first.usual, 1)}`;
  }
  if (first?.situation === "berth-overload") {
    return `Berth ${String(first.berth)}: ${number(first.expected)} ships expected, ${number(first.capacity)} ever held`;
  }
  return id;
}

/** Text that a model wrote: its lines as written, **bold** as bold, `code` as code. */
export function Prose({ text }: { text: string }) {
  return (
    <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
      {text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g).map((part, n) =>
        part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
          <b key={n}>{part.slice(2, -2)}</b>
        ) : part.startsWith("`") && part.endsWith("`") && part.length > 2 ? (
          <code key={n} className="font-mono text-[13px]">
            {part.slice(1, -1)}
          </code>
        ) : (
          part
        ),
      )}
    </div>
  );
}

/** How long ago a time was, in words: "3 minutes ago". `now` is the time of the page. */
export function ago(at: string | null | undefined, now: number): string {
  if (!at) return "never";
  const utc = /T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(at) ? `${at}Z` : at;
  const minutes = Math.round((now - new Date(utc).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  return `${Math.round(hours / 24)} days ago`;
}

/** A page title with a sentence under it. */
export function Title({ children, lead, aside }: { children: ReactNode; lead?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0 flex-1 basis-80">
        <h1 className="serif text-3xl leading-tight">{children}</h1>
        {lead ? <p className="mt-1.5 max-w-[68ch] text-[15px] text-muted">{lead}</p> : null}
      </div>
      {aside}
    </div>
  );
}

const OUTCOMES: Record<string, [string, string]> = {
  grounded: ["badge-calm", "Checked against the graph"],
  "not in the graph": ["badge-info", "Not in the graph"],
  unsupported: ["badge-warn", "Names something no tool showed"],
};

/** How the Desk agent found an answer: whether it rests on what its tools showed, and
 * what it looked at, in words. */
export function Trace({ found }: { found: Checked }) {
  const calls = (found.tools ?? []).filter((t) => t !== "none");
  const [tone, says] = OUTCOMES[found.outcome ?? ""] ?? [];
  return (
    <div className="mt-3 grid gap-2 text-xs">
      {found.model ? <p className="text-faint">Answered with {found.model}</p> : null}
      {calls.length ? (
        <ol className="flex flex-wrap gap-1.5">
          {calls.map((t, n) => (
            <li key={n} className="badge font-normal">
              {describeTool(t)}
            </li>
          ))}
        </ol>
      ) : null}
      {tone ? (
        <p className="flex flex-wrap items-center gap-2">
          <span className={`badge ${tone}`}>{says}</span>
          {found.unsupported?.length ? <span className="text-muted">{found.unsupported.join(", ")}</span> : null}
        </p>
      ) : null}
    </div>
  );
}
