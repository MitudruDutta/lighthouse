"use client";
import { Bot, KeyRound, Plug, ShieldCheck, Terminal } from "lucide-react";
import { useState } from "react";
import { CLIENTS, PLACEHOLDER, TOOLS, rest } from "../../lib/agents";
import type { State } from "./views";
import { Code, CopyButton, Tabs } from "./ui";

type Api = "curl" | "python" | "typescript";

export function AgentsView({
  s,
  api,
  secret,
}: {
  s: State;
  api: string;
  // A key created on this page, shown once: the snippets carry it until the page is left.
  secret: { name: string; secret: string } | null;
}) {
  const [client, setClient] = useState(CLIENTS[0].id);
  const [language, setLanguage] = useState<Api>("curl");
  const chosen = CLIENTS.find((item) => item.id === client) ?? CLIENTS[0];
  const key = secret?.secret ?? PLACEHOLDER;
  const samples = rest(api, key);
  return (
    <div className="cx-agents">
      <section className="cx-panel cx-endpoint">
        <div>
          <span className="cx-symbol">
            <Plug size={18} />
          </span>
          <div>
            <h2>MCP endpoint</h2>
            <p>
              Streamable HTTP. The key picks the project, its access picks the tools, and its name
              is the agent’s name in every entry it writes.
            </p>
          </div>
        </div>
        <label className="cx-field-copy">
          <span className="sr-only">MCP endpoint</span>
          <code>{s.mcp}</code>
          <CopyButton value={s.mcp} />
        </label>
      </section>

      <section className="cx-panel">
        <header className="cx-panel-head">
          <div>
            <h2>
              <span className="cx-step">1</span> A key for the agent
            </h2>
            <p>
              {secret
                ? `“${secret.name}” is in the snippets below. Copy them now: the key is not shown again.`
                : "Create a key named after the agent. The snippets below fill it in."}
            </p>
          </div>
          {secret ? (
            <span className="cx-pill" data-tone="good">
              <KeyRound size={13} /> Key ready
            </span>
          ) : (
            <button
              className="button button-small"
              disabled={!s.project}
              onClick={() => s.newKey(chosen.id)}
            >
              <KeyRound size={14} />
              Create a key for {chosen.name}
            </button>
          )}
        </header>
      </section>

      <section className="cx-panel">
        <header className="cx-panel-head">
          <div>
            <h2>
              <span className="cx-step">2</span> Add it to your agent
            </h2>
            <p>{chosen.where}</p>
          </div>
        </header>
        <Tabs
          label="Agent client"
          items={CLIENTS.map((item) => [item.id, item.name])}
          value={client}
          onChange={setClient}
        />
        <Code title={chosen.name} code={chosen.code(s.mcp, key)} note={chosen.note} />
      </section>

      <div className="cx-columns">
        <div className="cx-stack">
          <section className="cx-panel">
            <header className="cx-panel-head">
              <div>
                <h2>
                  <Terminal size={15} /> Claude Code plugin
                </h2>
                <p>
                  The MCP server and a skill that teaches Claude when to remember, recall, and
                  record episodes.
                </p>
              </div>
            </header>
            <Code
              title="In Claude Code"
              code="/plugin install lighthouse-memory --marketplace MitudruDutta/lighthouse"
              note="Before Claude Code 2.1.275: /plugin marketplace add MitudruDutta/lighthouse, then /plugin install lighthouse-memory@lighthouse."
            />
            <Code
              title="Before starting Claude Code"
              code={`export LIGHTHOUSE_MEMORY_URL=${api}\nexport LIGHTHOUSE_API_KEY=${key}`}
            />
          </section>
          <section className="cx-panel">
            <header className="cx-panel-head">
              <div>
                <h2>HTTP API</h2>
                <p>For servers and frameworks without MCP: the same operations under /v1.</p>
              </div>
              <a className="cx-link" href={`${api}/docs`}>
                API reference
              </a>
            </header>
            <Tabs
              label="Language"
              items={[
                ["curl", "cURL"],
                ["python", "Python"],
                ["typescript", "TypeScript"],
              ]}
              value={language}
              onChange={setLanguage}
            />
            <Code
              title={language === "curl" ? "cURL" : language === "python" ? "Python" : "TypeScript"}
              code={samples[language]}
            />
            <p className="cx-note">
              <ShieldCheck size={15} />
              Keys belong in agent configs and servers. Anyone with a key acts as that agent in
              this project.
            </p>
          </section>
        </div>
        <section className="cx-panel">
          <header className="cx-panel-head">
            <div>
              <h2>
                <Bot size={15} /> Tools the agent gets
              </h2>
              <p>A read-only key gets only the read tools.</p>
            </div>
          </header>
          <ul className="cx-tools">
            {TOOLS.map(([name, writes, text]) => (
              <li key={name}>
                <code>{name}</code>
                <span>{text}</span>
                <small data-tone={writes ? "write" : "read"}>{writes ? "write" : "read"}</small>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
