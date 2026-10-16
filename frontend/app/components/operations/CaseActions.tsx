"use client";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";
import { Check, CheckCheck, RotateCcw, Send, UserPlus } from "lucide-react";
import { updateCase } from "@/app/(app)/cases/actions";
import type { Case } from "@/app/lib/operations";
function Buttons({ item }: { item: Case }) {
  const { pending } = useFormStatus();
  if (item.status === "resolved")
    return (
      <button
        disabled={pending}
        name="operation"
        value="reopen"
        className="ops-outline"
      >
        <RotateCcw size={15} />
        Reopen case
      </button>
    );
  if (!item.owner)
    return (
      <button
        disabled={pending}
        name="operation"
        value="claim"
        className="ops-primary"
      >
        <UserPlus size={16} />
        {pending ? "Assigning…" : "Take ownership"}
      </button>
    );
  return (
    <div className="ops-decision-buttons">
      <button
        disabled={pending}
        name="operation"
        value="propose"
        className="ops-primary"
      >
        <Send size={15} />
        Propose next step
      </button>
      {item.action_status === "proposed" ? (
        <button
          disabled={pending}
          name="operation"
          value="approve"
          className="ops-outline"
        >
          <Check size={16} />
          Approve plan
        </button>
      ) : null}
      <button
        disabled={pending}
        name="operation"
        value="resolve"
        className="ops-outline"
      >
        <CheckCheck size={16} />
        Record outcome & resolve
      </button>
      <button
        disabled={pending}
        name="operation"
        value="release"
        className="ops-text-button"
      >
        Return to queue
      </button>
    </div>
  );
}
export default function CaseActions({ item }: { item: Case }) {
  const [state, action] = useActionState(updateCase, {});
  if (item.owner && !item.mine)
    return (
      <div className="ops-decision-note">
        {item.owner} owns this case. Their decisions and outcomes appear in the
        shared timeline.
      </div>
    );
  return (
    <form action={action} className="ops-decision-form">
      <input name="id" type="hidden" value={item.id} />
      <input name="revision" type="hidden" value={item.revision} />
      {item.owner && item.status !== "resolved" ? (
        <label>
          Next step or outcome
          <textarea
            name="text"
            rows={4}
            maxLength={2000}
            placeholder="What should happen next? Or what happened, and how was it resolved?"
          />
        </label>
      ) : null}
      <Buttons item={item} />
      {state.error ? (
        <p role="alert" className="ops-form-error">
          {state.error}
        </p>
      ) : state.saved ? (
        <p role="status" className="ops-form-success">
          {state.saved}
        </p>
      ) : null}
      {item.action_status === "approved" ? (
        <p className="ops-decision-note">
          Plan approved for your team. Coordinate execution through your usual
          operational channels.
        </p>
      ) : null}
    </form>
  );
}
