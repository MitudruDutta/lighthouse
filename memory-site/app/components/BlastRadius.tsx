"use client";
import { History, RotateCcw, ShieldAlert } from "lucide-react";
import { useState } from "react";

// An illustration of two library calls on a small record of agent work: as_of() reads the
// fact as it stood at any moment, and invalidate_entry() retracts an observation and returns
// everything that rested on it. The records are examples; the calls and their answers are
// the library's.
const VERSIONS = [
  { at: "09:14", value: 4, by: "watcher" },
  { at: "11:02", value: 6, by: "watcher" },
  { at: "13:40", value: 5, by: "reviewer" },
];
const NODES = [
  { id: "obs", x: 70, y: 70, kind: "Observation", text: "Berth VC2 expects 6 ships", hit: true },
  { id: "dec", x: 300, y: 70, kind: "Decision", text: "Move two calls to VC3", hit: true },
  { id: "hand", x: 530, y: 70, kind: "Handoff", text: "Desk: warn the agents", hit: true },
  { id: "lesson", x: 300, y: 205, kind: "Lesson", text: "VC2 overloads on Fridays", hit: true },
  { id: "other", x: 530, y: 205, kind: "Observation", text: "VC3 holds 5 ships", hit: false },
];
const EDGES: [string, string][] = [
  ["obs", "dec"],
  ["dec", "hand"],
  ["dec", "lesson"],
];

export function BlastRadius() {
  const [mode, setMode] = useState<"rewind" | "retract">("retract");
  const [moment, setMoment] = useState(1);
  const [retracted, setRetracted] = useState(false);
  const at = (id: string) => NODES.find((node) => node.id === id)!;
  const version = VERSIONS[moment];
  return (
    <div className="blast" data-retracted={(mode === "retract" && retracted) || undefined}>
      <div className="blast-modes" role="tablist" aria-label="What to show">
        <button
          role="tab"
          aria-selected={mode === "retract"}
          onClick={() => setMode("retract")}
        >
          <ShieldAlert size={15} /> Retract a fact
        </button>
        <button role="tab" aria-selected={mode === "rewind"} onClick={() => setMode("rewind")}>
          <History size={15} /> Rewind an answer
        </button>
        <span>Interactive illustration</span>
      </div>
      {mode === "retract" ? (
        <div className="blast-stage">
          <svg viewBox="0 0 640 270" role="img" aria-label="Records that rested on the observation">
            {EDGES.map(([from, to]) => (
              <line
                key={from + to}
                x1={at(from).x + 40}
                y1={at(from).y}
                x2={at(to).x - 40}
                y2={at(to).y}
                className="blast-edge"
              />
            ))}
            {NODES.map((node) => (
              <g key={node.id} className="blast-node" data-hit={node.hit || undefined}>
                <rect x={node.x - 60} y={node.y - 36} width="160" height="72" rx="10" />
                <text x={node.x - 46} y={node.y - 12} className="blast-kind">
                  {node.kind.toUpperCase()}
                </text>
                <foreignObject x={node.x - 48} y={node.y - 4} width="140" height="36">
                  <p>{node.text}</p>
                </foreignObject>
              </g>
            ))}
          </svg>
          <div className="blast-side">
            <p>
              {retracted
                ? "One call found the decision, the waiting handoff, and the lesson that rested on it. Nothing is deleted: the observation is marked retracted, with who did it and why."
                : "The watcher’s reading was wrong. Which decisions, handoffs, and lessons were built on it?"}
            </p>
            <button className="button button-small" onClick={() => setRetracted(!retracted)}>
              {retracted ? <RotateCcw size={14} /> : <ShieldAlert size={14} />}
              {retracted ? "Show it again" : "Retract the observation"}
            </button>
            <pre aria-label="The library call">
              {retracted
                ? `invalidate_entry(graph, "vc2-friday/1",
    by="reviewer", reason="feed sent a wrong ETA")
{"status": "invalidated",
 "impact": {
   "downstream_entries": ["vc2-friday/2"],
   "handoffs": ["warn-desk"],
   "lessons": ["vc2-fridays"], ...}}`
                : `impact_of_entry(graph, "vc2-friday/1")`}
            </pre>
          </div>
        </div>
      ) : (
        <div className="blast-stage blast-rewind">
          <div className="blast-timeline">
            {VERSIONS.map((item, index) => (
              <button
                key={item.at}
                aria-pressed={index === moment}
                onClick={() => setMoment(index)}
              >
                <i />
                <strong>{item.value} ships</strong>
                <small>
                  {item.at} · {item.by}
                </small>
              </button>
            ))}
          </div>
          <label className="blast-slider">
            <span>Ask as of</span>
            <input
              type="range"
              min={0}
              max={VERSIONS.length - 1}
              value={moment}
              onChange={(event) => setMoment(Number(event.target.value))}
            />
            <b>{version.at}</b>
          </label>
          <pre aria-label="The library call">
            {`as_of(graph, BERTH, "VC2", when)  # when: ${version.at}
{"expected": ${version.value}, "by": "${version.by}", ...}`}
          </pre>
          <p>
            Every version stays. An agent that acted at {version.at} saw {version.value} ships;
            you can ask what it saw, and who said so, long after the fact changed.
          </p>
        </div>
      )}
    </div>
  );
}
