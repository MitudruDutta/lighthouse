"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import { ask } from "./actions";
import type { ModelChoice } from "@/app/lib/api";

function Send({
  idle,
  busy,
  disabled = false,
}: {
  idle: string;
  busy: string;
  disabled?: boolean;
}) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending || disabled}
      className="disabled:opacity-60"
    >
      {pending ? busy : idle}
    </button>
  );
}

const SUGGESTED = [
  "Which ports of the world are unusual now, and why?",
  "Which Finnish berths expect more ships than they ever held?",
  "What has been learned about ports that go quiet?",
  "Show the last two weeks of port calls at Piraeus.",
];

export function Ask({
  session,
  fresh,
  models,
  selected,
  caseId,
  unavailable = false,
}: {
  session?: string;
  fresh?: boolean;
  models: ModelChoice[];
  selected?: string;
  caseId?: string;
  // The list of models could not be read. An empty list that was read means none is set up.
  unavailable?: boolean;
}) {
  const [error, action] = useActionState(ask, null);
  const [text, setText] = useState("");
  const ready = models.length > 0;
  return (
    <form action={action} className="grid gap-2">
      <input type="hidden" name="session" value={session ?? ""} />
      {caseId ? <input type="hidden" name="case_id" value={caseId} /> : null}
      {fresh && ready ? (
        <div className="mb-1 grid gap-2 sm:grid-cols-2">
          {(caseId
            ? [
                "What changed in this case, and which evidence supports it?",
                "What should we check before deciding the next step?",
              ]
            : SUGGESTED
          ).map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setText(q)}
              className="button-quiet h-full w-full !text-left !text-[13px] !font-normal"
            >
              {q}
            </button>
          ))}
        </div>
      ) : null}
      <div className="desk-model-choice">
        <label htmlFor="desk-model">Assistant model</label>
        <select
          id="desk-model"
          name="model"
          defaultValue={selected ?? models[0]?.id ?? ""}
          disabled={!ready}
        >
          {ready ? (
            models.map((choice) => (
              <option key={choice.id} value={choice.id}>
                {choice.provider} · {choice.model}
              </option>
            ))
          ) : (
            <option value="">
              {unavailable ? "Temporarily unavailable" : "No model set up"}
            </option>
          )}
        </select>
        <p>
          {ready
            ? "Choose a model for your next question. Memory stays with this session."
            : unavailable
              ? "Your conversations are saved. The assistant is temporarily unavailable."
              : "The Desk needs a model to answer. An administrator adds a model API key to .env and runs ./setup.sh again. Monitoring, cases, and search work without one."}
        </p>
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        name="text"
        rows={3}
        required
        maxLength={4000}
        disabled={!ready}
        placeholder={
          ready
            ? "Ask the desk: which ports in India are unusual now? What waits at berth VC2?"
            : "The Desk answers once a model is set up."
        }
        className="w-full rounded-md border p-2 text-sm disabled:opacity-60"
        style={{
          borderColor: "var(--line)",
          background: "var(--panel)",
          color: "var(--text)",
        }}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Send
          idle="Ask"
          busy="The desk is looking into it…"
          disabled={!ready}
        />
        {error ? (
          <p className="text-sm" style={{ color: "var(--hot)" }}>
            {error}
          </p>
        ) : null}
      </div>
    </form>
  );
}
