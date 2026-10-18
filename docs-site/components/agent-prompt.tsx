"use client";
import { useState } from "react";
import { Bot, Check, Copy } from "lucide-react";

/** The setup prompt for a coding agent; links point at these docs wherever they are served. */
function prompt(docs: string) {
  return `Set up Lighthouse Memory in this project.

Lighthouse Memory is a Python library that keeps an agent's facts in a FalkorDB graph, with every version of every fact and the evidence behind it. It is published on PyPI as lighthouse-graph and imported as lighthouse. It needs Python 3.12 or later.

1. Install it: pip install lighthouse-graph (or uv add lighthouse-graph if the project uses uv).
2. Make sure a FalkorDB is running. For local work: docker run -p 6379:6379 -it --rm falkordb/falkordb:6.0.2. Keep to FalkorDB 6.0.2; the library is tested on it.
3. Declare a Kind for each kind of thing the project must remember. Call ensure_schema(graph, kinds) once at start, write rows with remember(), and read them back with history() and as_of().
4. Add one small check that writes a row and reads it back, and run it.

Quickstart: ${docs}/library
Python API reference: ${docs}/reference
Hosted Memory API and MCP server, instead of a local FalkorDB: ${docs}/memory-api and ${docs}/mcp

Ask me before you decide what to store. Use only functions the reference lists.`;
}

/** A button that copies the setup prompt, for pasting into Claude Code. */
export function AgentPrompt() {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="agent-prompt not-prose"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(prompt(window.location.origin));
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch {
          setCopied(false);
        }
      }}
    >
      <Bot size={17} aria-hidden />
      <span>
        <strong>{copied ? "Copied. Paste it into your agent" : "Copy setup prompt for Claude Code"}</strong>
        <small>Paste it into Claude Code; it sets up the library</small>
      </span>
      {copied ? <Check size={15} aria-hidden /> : <Copy size={15} aria-hidden />}
    </button>
  );
}
