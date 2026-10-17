"use client";
import { Check, Copy, Database } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Fact, Summary } from "../../lib/types";

// The server and the browser must write a time alike, or React refuses the page it
// hydrates (error 418): one locale, and the time zone of the user's profile.
export const LOCALE = "en-GB";

export function day(value: number | null, zone: string) {
  if (!value) return "Not used yet";
  try {
    return new Date(value * 1000).toLocaleDateString(LOCALE, {
      year: "numeric",
      month: "short",
      day: "numeric",
      timeZone: zone,
    });
  } catch {
    return new Date(value * 1000).toISOString().slice(0, 10);
  }
}

export function moment(at: number, zone: string) {
  try {
    return new Intl.DateTimeFormat(LOCALE, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: zone,
    }).format(new Date(at * 1000));
  } catch {
    return new Date(at * 1000).toISOString().slice(0, 16).replace("T", " ") + " UTC";
  }
}

export const OPERATIONS: Record<string, string> = {
  "api.write": "Memory written",
  "api.read": "Memories recalled",
  "api.history": "History read",
  "api.connection": "Connection traced",
  "api.episode": "Episode opened",
  "api.episode.read": "Episode read",
  "api.entry": "Episode entry recorded",
  "api.task": "Task changed",
  "api.handoff": "Handoff given or accepted",
  "api.handoff.read": "Handoffs read",
  "console.write": "Memory saved in console",
};

export function CopyButton({
  value,
  label = "Copy",
  quiet = false,
}: {
  value: string;
  label?: string;
  quiet?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className={quiet ? "cx-copy cx-copy-quiet" : "cx-copy"}
      aria-label={quiet ? label : undefined}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch {
          setCopied(false);
        }
      }}
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
      {quiet ? null : copied ? "Copied" : label}
    </button>
  );
}

export function Code({
  title,
  code,
  note,
}: {
  title: string;
  code: string;
  note?: string;
}) {
  return (
    <figure className="cx-code">
      <figcaption>
        <span>{title}</span>
        <CopyButton value={code} />
      </figcaption>
      <pre tabIndex={0}>{code}</pre>
      {note ? <p>{note}</p> : null}
    </figure>
  );
}

export function Tabs<T extends string>({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: [T, string][];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="cx-tabs" role="tablist" aria-label={label}>
      {items.map(([id, name]) => (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={value === id}
          onClick={() => onChange(id)}
        >
          {name}
        </button>
      ))}
    </div>
  );
}

export function Empty({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="cx-empty">
      <span>
        <Database size={22} />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}

// A menu that closes on Escape or on a click outside it.
export function useMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  return [open, setOpen, ref] as const;
}

export function Spark({ days }: { days: Summary["days"] }) {
  if (days.length < 2) return null;
  const most = Math.max(...days.map((item) => item.count), 1);
  const points = days
    .map((item, index) => {
      const x = (index / (days.length - 1)) * 100;
      const y = 28 - (item.count / most) * 26;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="cx-spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden>
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function MemoryGraph({
  facts,
  edges,
  select,
  loading = false,
}: {
  facts: Fact[];
  edges: Summary["edges"];
  select: (fact: Fact) => void;
  // The project is still being read: no memories yet does not mean none.
  loading?: boolean;
}) {
  const nodes = facts.slice(0, 12);
  const height = nodes.length <= 3 ? 220 : 340;
  const point = (index: number) => {
    if (nodes.length === 1) return { x: 320, y: height / 2 };
    if (nodes.length === 2) return { x: index === 0 ? 180 : 460, y: height / 2 };
    const angle = (index / nodes.length) * Math.PI * 2 - Math.PI / 2;
    return {
      x: 320 + Math.cos(angle) * 210,
      y: height / 2 + Math.sin(angle) * (height / 2 - 45),
    };
  };
  if (!nodes.length)
    return loading ? (
      <p className="cx-loading" role="status">
        Loading this project’s memories…
      </p>
    ) : (
      <Empty
        title="Your graph has room to grow."
        text="Add memories and link them to each other. Their connections appear here."
      />
    );
  return (
    <div className="cx-graph">
      <svg
        viewBox={`0 0 640 ${height}`}
        // A group, not an image: each memory in it is a button.
        role="group"
        aria-label="Project memory relationships"
      >
        <defs>
          <pattern id="cx-grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r=".7" style={{ fill: "var(--cx-line)" }} />
          </pattern>
        </defs>
        <rect width="640" height={height} fill="url(#cx-grid)" />
        {edges.map((edge, i) => {
          const a = nodes.findIndex((node) => node.key === edge.from),
            b = nodes.findIndex((node) => node.key === edge.to);
          if (a < 0 || b < 0) return null;
          return (
            <line
              key={i}
              x1={point(a).x}
              y1={point(a).y}
              x2={point(b).x}
              y2={point(b).y}
              style={{ stroke: "var(--cx-link)" }}
              strokeWidth="1.5"
            />
          );
        })}
        {nodes.map((fact, index) => {
          const p = point(index);
          return (
            <g
              key={fact.key}
              role="button"
              tabIndex={0}
              aria-label={`Inspect ${fact.title}`}
              onClick={() => select(fact)}
              onKeyDown={(event) => {
                if (["Enter", " "].includes(event.key)) {
                  event.preventDefault();
                  select(fact);
                }
              }}
            >
              <title>{`${fact.title} · ${fact.key}`}</title>
              <rect
                x={p.x - 90}
                y={p.y - 20}
                width="180"
                height="40"
                rx="8"
                style={{ fill: "var(--cx-surface)", stroke: "var(--cx-line-hover)" }}
              />
              <circle cx={p.x - 75} cy={p.y} r="3" style={{ fill: "var(--cx-accent)" }} />
              <text x={p.x - 64} y={p.y + 4} style={{ fill: "var(--cx-ink)" }} fontSize="12">
                {fact.title.length > 24 ? fact.title.slice(0, 23) + "…" : fact.title}
              </text>
            </g>
          );
        })}
      </svg>
      <footer>
        <span>
          <i />
          Current links
        </span>
        <span>
          {nodes.length} of {facts.length} memories shown
        </span>
      </footer>
    </div>
  );
}
