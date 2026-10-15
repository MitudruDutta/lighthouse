"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import { ask, signIn } from "./actions";
import type { ModelChoice } from "@/app/lib/api";

function Send({ idle, busy, disabled = false }: { idle: string; busy: string; disabled?: boolean }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending || disabled} className="disabled:opacity-60">
      {pending ? busy : idle}
    </button>
  );
}

export function SignIn() {
  const [error, action] = useActionState(signIn, null);
  return (
    <form action={action} className="grid max-w-md gap-2">
      <label htmlFor="token" className="text-sm text-muted">
        Desk token
      </label>
      <input id="token" name="token" type="password" autoComplete="current-password" required />
      <div>
        <Send idle="Sign in" busy="Checking…" />
      </div>
      {error ? <p className="text-sm" style={{ color: "var(--hot)" }}>{error}</p> : null}
    </form>
  );
}

const SUGGESTED = [
  "Which ports of the world are unusual now, and why?",
  "Which Finnish berths expect more ships than they ever held?",
  "What has been learned about ports that go quiet?",
  "Show the last two weeks of port calls at Piraeus.",
];

export function Ask({ session, fresh, models, selected }: { session?: string; fresh?: boolean; models: ModelChoice[]; selected?: string }) {
  const [error, action] = useActionState(ask, null);
  const [text, setText] = useState("");
  return (
    <form action={action} className="grid gap-2">
      <input type="hidden" name="session" value={session ?? ""} />
      {fresh ? (
        <div className="mb-1 grid gap-2 sm:grid-cols-2">
          {SUGGESTED.map((q) => (
            <button key={q} type="button" onClick={() => setText(q)} className="button-quiet h-full w-full !text-left !text-[13px] !font-normal">
              {q}
            </button>
          ))}
        </div>
      ) : null}
      <div className="desk-model-choice">
        <label htmlFor="desk-model">Assistant model</label>
        <select id="desk-model" name="model" defaultValue={selected ?? models[0]?.id ?? ""} disabled={!models.length}>
          {models.length ? models.map(choice => <option key={choice.id} value={choice.id}>{choice.provider} · {choice.model}</option>) : <option value="">Temporarily unavailable</option>}
        </select>
        <p>{models.length ? "Choose a model for your next question. Memory stays with this session." : "Your conversations are saved. The assistant is temporarily unavailable."}</p>
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        name="text"
        rows={3}
        required
        maxLength={4000}
        placeholder="Ask the desk: which ports in India are unusual now? What waits at berth VC2?"
        className="w-full rounded-md border p-2 text-sm"
        style={{ borderColor: "var(--line)", background: "var(--panel)", color: "var(--text)" }}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Send idle="Ask" busy="The desk is looking into it…" disabled={!models.length} />
        {error ? <p className="text-sm" style={{ color: "var(--hot)" }}>{error}</p> : null}
      </div>
    </form>
  );
}
