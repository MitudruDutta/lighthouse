"use client";
import { useEffect, useState } from "react";
import { MemoryBeacon } from "./MemoryBeacon";
import {
  ArrowRight,
  Check,
  Copy,
  GitBranch,
  History as HistoryIcon,
  Layers3,
  Pause,
  Play,
  Search,
} from "lucide-react";
const MODES = [
  {
    name: "Write",
    icon: Layers3,
    label: "A fact changes. Its history stays.",
    steps: [
      ["Observation", "Deployment needs review.", "Context received"],
      ["Preserved state", "Nothing lost.", "v1 → v2 → v3"],
      ["Connected evidence", "Evidence retained", "Linked to its source"],
    ],
  },
  {
    name: "Recall",
    icon: Search,
    label: "Follow relationships. Retrieve the context.",
    steps: [
      ["Question", "Why was this flagged?", "Asked by an agent"],
      ["Graph walk", "Connected evidence", "Observation → change"],
      ["Answer", "Relevant context", "Every step traceable"],
    ],
  },
  {
    name: "Coordinate",
    icon: GitBranch,
    label: "Pass the work. Keep the evidence.",
    steps: [
      ["Watcher", "New evidence found.", "Agent A"],
      ["Task claim", "Atomic task claim", "One owner, with a lease"],
      ["Hand-off", "Ready for the next agent.", "Agent B"],
    ],
  },
];
const STEP_ICONS = [Layers3, HistoryIcon, GitBranch];
export function MemoryFlow() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    const page = document.querySelector(".marketing");
    page?.classList.toggle("motion-paused", paused);
    return () => page?.classList.remove("motion-paused");
  }, [paused]);
  const mode = MODES[active];
  return (
    <div
      className={`memory-flow ${paused ? "is-paused" : ""}`}
      data-mode={active}
    >
      <div className="flow-toolbar">
        <span>
          <i /> THE CONTEXT ENGINE
        </span>
        <button
          type="button"
          className="icon-button"
          aria-label={
            paused ? "Play diagram animation" : "Pause diagram animation"
          }
          onClick={() => setPaused(!paused)}
        >
          {paused ? <Play size={15} /> : <Pause size={15} />}
        </button>
      </div>
      <div className="signal-stage">
        <MemoryBeacon paused={paused} mode={active} />
      </div>
      <ol className="signal-trail" key={active} aria-label={`${mode.name}, step by step`}>
        {mode.steps.map(([kicker, title, detail], index) => {
          const Icon = STEP_ICONS[index];
          return (
            <li key={kicker}>
              <span>
                <Icon size={12} aria-hidden />
                {kicker}
              </span>
              <strong>{title}</strong>
              <small>{detail}</small>
            </li>
          );
        })}
      </ol>
      <div
        className="flow-tabs"
        role="group"
        aria-label="Explore memory workflows"
      >
        {MODES.map((item, index) => (
          <button
            key={item.name}
            type="button"
            aria-pressed={active === index}
            onClick={() => setActive(index)}
          >
            <item.icon size={15} />
            {item.name}
            <ArrowRight size={13} />
          </button>
        ))}
      </div>
      <p className="flow-caption" aria-live="polite">
        {mode.label}
        <span>Interactive illustration</span>
      </p>
    </div>
  );
}
export function CodeExample() {
  const [tab, setTab] = useState(0);
  const [copied, setCopied] = useState(false);
  const code =
    tab === 0
      ? `curl "$LIGHTHOUSE_MEMORY_URL/v1/memories" \\\n  -H "Authorization: Bearer $LIGHTHOUSE_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '{\n    "key": "decision-001",\n    "title": "A decision worth remembering",\n    "text": "Reviewed the evidence. Follow up tomorrow.",\n    "metadata": { "agent": "reviewer" }\n  }'`
      : `from lighthouse import Kind, remember, history, now\n\nDEVICE = Kind("Device", key="serial")\n\nremember(graph, DEVICE, by="watcher", rows=[\n    {"key": "sensor-01", "t": now(),\n     "values": {"status": "reviewed"}}\n])\n\nhistory(graph, DEVICE, "sensor-01")`;
  return (
    <div className="code-example">
      <div className="code-tabs">
        <div>
          {["Memory API", "Python library"].map((name, index) => (
            <button
              key={name}
              aria-pressed={tab === index}
              onClick={() => setTab(index)}
            >
              {name}
            </button>
          ))}
        </div>
        <button
          aria-label="Copy code example"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(code);
              setCopied(true);
              setTimeout(() => setCopied(false), 1800);
            } catch {
              setCopied(false);
            }
          }}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>
      <pre tabIndex={0}>
        <code>{code}</code>
      </pre>
      <div className="code-caption">
        <span className="status-dot" />
        Structured memory. No model call required.
        <ArrowRight size={14} />
      </div>
    </div>
  );
}
