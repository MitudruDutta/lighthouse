import Link from "next/link";
import type { ReactNode } from "react";

import { type Entry, type Ref, segments } from "../lib/api";

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
      return `/berths#${encodeURIComponent(id)}`;
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
        <header className="mb-3 flex items-baseline justify-between gap-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>
          {aside ? <div className="text-xs text-faint">{aside}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
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
};

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${TONES[tone ?? String(children)] ?? ""}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-faint">{children}</p>;
}

export function Loading({ what }: { what: string }) {
  return <p className="py-10 text-center text-sm text-faint">Reading {what}…</p>;
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
