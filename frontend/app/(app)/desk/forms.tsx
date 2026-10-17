"use client";

import { useActionState, useRef, useState } from "react";
import { useFormStatus } from "react-dom";
import { ArrowUp, BookOpen, Globe2, Ship, TrendingDown } from "lucide-react";

import { ask } from "./actions";
import type { ModelChoice } from "@/app/lib/api";

const SUGGESTED = [
  { text: "Which ports of the world are unusual now, and why?", icon: Globe2 },
  { text: "Which Finnish berths expect more ships than they ever held?", icon: Ship },
  { text: "What has been learned about ports that go quiet?", icon: BookOpen },
  { text: "Show the last two weeks of port calls at Piraeus.", icon: TrendingDown },
];
const FOR_A_CASE = [
  { text: "What changed in this case, and which evidence supports it?", icon: BookOpen },
  { text: "What should we check before deciding the next step?", icon: Ship },
];

// While the Desk works, the question shows at once, with what it is doing.
function Waiting() {
  const { pending, data } = useFormStatus();
  if (!pending) return null;
  return (
    <div className="desk-waiting" role="status">
      <p className="desk-bubble desk-bubble-user">{String(data?.get("text") ?? "")}</p>
      <p className="desk-thinking">
        <span aria-hidden>
          <i />
          <i />
          <i />
        </span>
        The desk is reading the graph…
      </p>
    </div>
  );
}

function Send({ disabled }: { disabled: boolean }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className="desk-send" disabled={pending || disabled} aria-label="Ask the desk">
      <ArrowUp size={18} />
    </button>
  );
}

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
  const [text, setText] = useState("");
  // The box is cleared when a question is sent; a question that was refused comes back.
  const [error, action] = useActionState(async (previous: string | null, form: FormData) => {
    const refused = await ask(previous, form);
    if (refused) setText(String(form.get("text") ?? ""));
    return refused;
  }, null);
  const box = useRef<HTMLTextAreaElement>(null);
  const ready = models.length > 0;
  const suggestions = caseId ? FOR_A_CASE : SUGGESTED;
  return (
    <form action={action} className="desk-ask" onSubmit={() => setText("")}>
      <input type="hidden" name="session" value={session ?? ""} />
      {caseId ? <input type="hidden" name="case_id" value={caseId} /> : null}
      {fresh && ready ? (
        <div className={caseId ? "desk-suggest desk-suggest-compact" : "desk-suggest"}>
          {suggestions.map(({ text: question, icon: Icon }) => (
            <button
              key={question}
              type="button"
              onClick={() => {
                setText(question);
                box.current?.focus();
              }}
            >
              <Icon size={16} aria-hidden />
              <span>{question}</span>
            </button>
          ))}
        </div>
      ) : null}
      <Waiting />
      <div className="desk-composer" data-disabled={!ready || undefined}>
        <label htmlFor="desk-question" className="sr-only">
          Your question
        </label>
        <textarea
          id="desk-question"
          ref={box}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            // Enter asks; Shift+Enter starts a new line.
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (text.trim()) event.currentTarget.form?.requestSubmit();
            }
          }}
          name="text"
          rows={2}
          required
          maxLength={4000}
          disabled={!ready}
          placeholder={
            ready
              ? "Ask about ports, berths, ships, or what was learned…"
              : "The Desk answers once a model is set up."
          }
        />
        <div className="desk-composer-bar">
          <label className="desk-model">
            <span className="sr-only">Assistant model</span>
            <select name="model" defaultValue={selected ?? models[0]?.id ?? ""} disabled={!ready}>
              {ready ? (
                models.map((choice) => (
                  <option key={choice.id} value={choice.id}>
                    {choice.provider} · {choice.model}
                  </option>
                ))
              ) : (
                <option value="">{unavailable ? "Temporarily unavailable" : "No model set up"}</option>
              )}
            </select>
          </label>
          <span className="desk-count">{text.length ? `${text.length} / 4000` : "Enter to ask · Shift+Enter for a new line"}</span>
          <Send disabled={!ready || !text.trim()} />
        </div>
      </div>
      {!ready ? (
        <p className="desk-note">
          {unavailable
            ? "Your conversations are saved. The assistant is temporarily unavailable."
            : "The Desk needs a model to answer. An administrator adds a model API key and restarts it. Monitoring, cases, and search work without one."}
        </p>
      ) : null}
      {error ? (
        <p className="desk-error" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
