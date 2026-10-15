"use client";

import { useState } from "react";
import { ArrowRight, Check, GitBranch, History, RotateCcw } from "lucide-react";

const STATES = [
  {
    status: "Observed",
    agent: "Watcher",
    time: "09:14",
    text: "A deployment changed the service configuration.",
    evidence: "Deployment event → affected service",
  },
  {
    status: "Investigated",
    agent: "Investigator",
    time: "09:26",
    text: "The change connects to a configuration mismatch.",
    evidence: "Deployment event → configuration change → finding",
  },
  {
    status: "Resolved",
    agent: "Reviewer",
    time: "10:03",
    text: "The fix is verified. Its evidence and earlier states remain.",
    evidence: "Finding → corrective change → verified outcome",
  },
];

export function MemoryWalkthrough({ docs }: { docs: string }) {
  const [step, setStep] = useState(0);
  const [selected, setSelected] = useState(0);
  const state = STATES[selected];
  return (
    <section
      className="section walkthrough"
      aria-labelledby="walkthrough-title"
    >
      <div className="walkthrough-intro">
        <span className="eyebrow">03 / TRY THE MEMORY MODEL</span>
        <h2 id="walkthrough-title">
          Change the fact.
          <br />
          Keep the story.
        </h2>
        <p>
          Advance an investigation, then revisit an earlier state. The current
          answer changes; the evidence behind it stays connected.
        </p>
        <div className="walkthrough-actions">
          <button
            className="button"
            disabled={step === STATES.length - 1}
            onClick={() => {
              setStep(step + 1);
              setSelected(step + 1);
            }}
          >
            {step === 0
              ? "Investigate the change"
              : step === 1
                ? "Record the resolution"
                : "History preserved"}
            {step === 2 ? <Check size={17} /> : <ArrowRight size={17} />}
          </button>
          <button
            className="walkthrough-reset"
            onClick={() => {
              setStep(0);
              setSelected(0);
            }}
            aria-label="Reset memory walkthrough"
          >
            <RotateCcw size={16} />
            Reset
          </button>
        </div>
        <span className="demo-disclosure">
          Browser illustration · No data sent or saved
        </span>
        <div className="memory-capabilities">
          <a href={`${docs}/episodes`}>
            Episodes & evidence <ArrowRight size={14} />
          </a>
          <a href={`${docs}/learning`}>
            Lessons & playbooks <ArrowRight size={14} />
          </a>
          <a href={`${docs}/coordination`}>
            Claims & handoffs <ArrowRight size={14} />
          </a>
        </div>
      </div>
      <div className="walkthrough-record">
        <header>
          <span>
            <History size={17} />
            Versioned memory
          </span>
          <code>deployment-42</code>
        </header>
        <div
          className="walkthrough-timeline"
          role="group"
          aria-label="Inspect a stored memory version"
        >
          {STATES.map((item, index) => (
            <button
              key={item.status}
              disabled={index > step}
              aria-pressed={selected === index}
              onClick={() => setSelected(index)}
            >
              <span
                className={
                  index <= step ? "timeline-point is-stored" : "timeline-point"
                }
              >
                {index < step ? <Check size={12} /> : index + 1}
              </span>
              <strong>{item.status}</strong>
              <small>{item.time} UTC</small>
            </button>
          ))}
        </div>
        <div className="walkthrough-state" key={selected} aria-live="polite">
          <span className="record-status">
            {selected === step
              ? "CURRENT STATE"
              : "EARLIER STATE · STILL AVAILABLE"}
          </span>
          <h3>{state.status}</h3>
          <p>{state.text}</p>
          <dl>
            <div>
              <dt>Recorded by</dt>
              <dd>{state.agent}</dd>
            </div>
            <div>
              <dt>Stored versions</dt>
              <dd>{step + 1}</dd>
            </div>
          </dl>
          <div className="evidence-path">
            <GitBranch size={18} />
            <span>{state.evidence}</span>
          </div>
        </div>
        <footer>
          <Check size={15} />
          {step === 0
            ? "Ready for the next observation."
            : `${step + 1} versions stored. Click an earlier state to inspect it.`}
        </footer>
      </div>
    </section>
  );
}
