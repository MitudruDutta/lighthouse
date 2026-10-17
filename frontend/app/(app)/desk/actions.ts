"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { type Answer, DESK_COOKIE as COOKIE, desk } from "@/app/lib/api";
import { caseHref } from "@/app/lib/operations";

const SESSION = /^[A-Za-z0-9_-]{1,64}$/;

/** Ask the Desk, in the session of the form or a new one. */
export async function ask(
  _: string | null,
  form: FormData,
): Promise<string | null> {
  const token = (await cookies()).get(COOKIE)?.value;
  if (!token) return "Sign in first.";
  const text = String(form.get("text") ?? "").trim();
  if (!text) return "Ask something.";
  if (text.length > 4000) return "Ask in at most 4,000 characters.";
  const given = String(form.get("session") ?? "");
  const session = SESSION.test(given) ? given : crypto.randomUUID();
  const model = String(form.get("model") ?? "");
  const caseId = String(form.get("case_id") ?? "").slice(0, 200);
  const answer = await desk<Answer>("/api/desk/ask", token, {
    session,
    text,
    ...(model ? { model } : {}),
    ...(caseId ? { case_id: caseId } : {}),
  });
  if (!answer.ok) {
    if (answer.status === 401)
      return "Your session has expired. Please sign in again.";
    if (answer.status === 400)
      return "That model is unavailable. Choose another model and try again.";
    if (answer.status === 422)
      return "Ask in plain words, in at most 4,000 characters.";
    return "The desk agent could not answer just now. Try again in a moment.";
  }
  redirect(
    `${caseId ? caseHref(caseId) : "/desk/chat"}?session=${session}${model ? `&model=${encodeURIComponent(model)}` : ""}${caseId ? "#case-conversation" : ""}`,
  );
}
