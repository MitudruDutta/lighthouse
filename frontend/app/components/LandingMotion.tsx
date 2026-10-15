"use client";

import { ArrowRight, ArrowUpRight, BookOpenCheck, Bot, Check, Database, GitBranch, Layers3, Pause, Play, Radar, Ship } from "lucide-react";
import Link from "next/link";
import type { CSSProperties, PointerEvent, ReactNode } from "react";
import { useState } from "react";

export function MotionCard({ className = "", children }: { className?: string; children: ReactNode }) {
  function tilt(event: PointerEvent<HTMLElement>) {
    if (event.pointerType !== "mouse" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const box = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty("--tilt-x", `${-(event.clientY - box.top - box.height / 2) / box.height * 2}deg`);
    event.currentTarget.style.setProperty("--tilt-y", `${(event.clientX - box.left - box.width / 2) / box.width * 2}deg`);
  }
  return <article className={`bento-card ${className}`} onPointerMove={tilt} onPointerLeave={(event) => { event.currentTarget.style.setProperty("--tilt-x", "0deg"); event.currentTarget.style.setProperty("--tilt-y", "0deg"); }}>{children}</article>;
}

const MEMORIES = [
  { name: "Episodic", label: "What happened", title: "The whole story, in order.", description: "Observations, actions and outcomes stay together in an episode.", icon: Layers3, to: "/episodes", tag: "Episode → evidence → outcome" },
  { name: "Semantic", label: "What it means", title: "Lessons with receipts.", description: "Completed episodes support or contradict a lesson. Its evidence stays attached.", icon: BookOpenCheck, to: "/learned", tag: "Lesson → supporting episodes" },
  { name: "Procedural", label: "What works", title: "A better way next time.", description: "Versioned playbooks remember successful repeated steps and their outcomes.", icon: GitBranch, to: "/learned", tag: "Playbook → steps → outcomes" },
];
export function MemoryCards() {
  const [active, setActive] = useState(0);
  return <>
    <header className="bento-heading"><span className="feature-index">02 / REMEMBER</span><Database size={19} aria-hidden /></header>
    <h3 className="display">Memory with<br />some depth.</h3><p className="bento-description">Three ways to remember. One connected graph.</p>
    <div className="memory-card-stack" aria-live="polite">{MEMORIES.map((memory, index) => {
      const order = (index - active + 3) % 3;
      return <div key={memory.name} className={`memory-layer memory-layer-${index}`} style={{ "--order": order } as CSSProperties} aria-hidden={order !== 0}><memory.icon size={22} strokeWidth={1.5} aria-hidden /><span>{memory.label}</span><strong>{memory.title}</strong><p>{memory.description}</p><small>{memory.tag}</small></div>;
    })}</div>
    <div className="memory-select" role="group" aria-label="Explore memory types">{MEMORIES.map((memory, index) => <button key={memory.name} type="button" aria-pressed={active === index} onClick={() => setActive(index)}>{memory.name}{active === index ? <Check size={11} aria-hidden /> : null}</button>)}</div>
    <Link href={MEMORIES[active].to} className="bento-link">Explore {MEMORIES[active].name.toLowerCase()} memory<ArrowUpRight size={14} aria-hidden /></Link>
  </>;
}

const ENTITIES = [
  { name: "Vessel", icon: Ship, x: 18, y: 50, text: "Vessels connect to the port calls in which they appear." },
  { name: "Port call", icon: Layers3, x: 50, y: 28, text: "A port call links a ship to its arrival, destination and assigned berth." },
  { name: "Berth", icon: Database, x: 82, y: 50, text: "Berth assignments reveal expected overlap and related arrival history." },
  { name: "Episode", icon: GitBranch, x: 50, y: 78, text: "Episodes connect operational entities to observations, actions and outcomes." },
];
export function ConnectedDiagram() {
  const [active, setActive] = useState(1);
  return <>
    <header className="bento-heading"><span className="feature-index">03 / INVESTIGATE</span><GitBranch size={19} aria-hidden /></header>
    <h3 className="display">Follow the thread.<br />Find the next move.</h3>
    <div className="connection-illustration" aria-label="Illustration of relationships between vessels, port calls, berths and episodes">
      <svg viewBox="0 0 500 220" aria-hidden><path d="M90,110 Q90,62 250,62 T410,110 M90,110 Q90,172 250,172 T410,110 M250,62 L250,172" fill="none" stroke="currentColor" strokeWidth="1.2" /><path className="flow-line" d="M90,110 Q90,62 250,62 T410,110" fill="none" stroke="var(--beam)" strokeWidth="2" strokeDasharray="5 55" /></svg>
      {ENTITIES.map((entity, index) => <button key={entity.name} type="button" className="diagram-entity" style={{ left: `${entity.x}%`, top: `${entity.y}%` }} aria-pressed={active === index} onClick={() => setActive(index)}><entity.icon size={18} strokeWidth={1.5} aria-hidden /><span>{entity.name}</span></button>)}
    </div>
    <p className="diagram-caption" aria-live="polite">{ENTITIES[active].text}</p><Link href="/investigate" className="bento-link">Open graph investigations<ArrowUpRight size={14} aria-hidden /></Link>
  </>;
}

const CREW = [
  { name: "Watcher", action: "Spot the overlap", icon: Radar, text: "Checks expected berth overlap against the highest overlap previously observed." },
  { name: "Port Watcher", action: "Find the change", icon: Ship, text: "Compares daily global port activity with a 28-day baseline and records unusual spells." },
  { name: "Desk agent", action: "Work the evidence", icon: Bot, text: "Selects MCP graph tools, investigates handoffs, and records an assessment linked to evidence." },
  { name: "Reviewer", action: "Keep the lesson", icon: BookOpenCheck, text: "Uses completed episodes to update lessons and learn repeated successful procedures." },
];
export function AgentRelay() {
  const [active, setActive] = useState(2);
  return <>
    <header className="bento-heading"><span className="feature-index">04 / COORDINATE</span><Bot size={19} aria-hidden /></header>
    <div className="crew-bento-body"><div><h3 className="display">Different agents.<br />Shared bearings.</h3><p className="bento-description">Evidence moves with the handoff. Context stays in memory.</p><p className="crew-explanation" aria-live="polite">{CREW[active].text}</p><Link href="/agents" className="bento-link">Meet the crew<ArrowUpRight size={14} aria-hidden /></Link></div>
    <ol className="crew-cards">{CREW.map((agent, index) => <li key={agent.name}><button type="button" aria-pressed={active === index} onClick={() => setActive(index)}><span className="crew-icon"><agent.icon size={17} aria-hidden /></span><span><strong>{agent.name}</strong><small>{agent.action}</small></span><span className="crew-number">0{index + 1}</span></button></li>)}</ol></div>
  </>;
}

const TOPICS = ["Connected data", "Temporal history", "MCP graph tools", "Persistent memory", "Agent handoffs", "Evidence trails"];
export function MemoryTape() {
  const [paused, setPaused] = useState(false);
  return <div className={`memory-tape ${paused ? "is-paused" : ""}`}>
    <div className="memory-tape-window"><div className="memory-tape-track">{[0, 1].map((copy) => <div key={copy} aria-hidden={copy === 1}>{TOPICS.map((topic) => <span key={topic}><i />{topic}<ArrowRight size={13} aria-hidden /></span>)}</div>)}</div></div>
    <button type="button" aria-label={paused ? "Play feature cards" : "Pause feature cards"} onClick={() => setPaused(!paused)}>{paused ? <Play size={13} aria-hidden /> : <Pause size={13} aria-hidden />}</button>
  </div>;
}
