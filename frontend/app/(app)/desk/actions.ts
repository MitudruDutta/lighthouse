"use server";

import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import { type Answer, DESK_COOKIE as COOKIE, type Session, desk } from "@/app/lib/api";

const TOKEN = /^[A-Za-z0-9_-]{32,}$/;
const SESSION = /^[A-Za-z0-9_-]{1,64}$/;

/** Sign in with a desk token. The API checks it; the screen keeps it in a cookie that the
 * page's scripts cannot read, and sends it with every question. */
export async function signIn(_: string | null, form: FormData): Promise<string | null> {
  const token = String(form.get("token") ?? "").trim();
  if (!TOKEN.test(token)) return "A desk token has at least 32 letters and digits.";
  const check = await desk<Session[]>("/api/desk/sessions", token);
  if (!check.ok) return check.status === 401 ? "That is not a token of this desk." : "The desk cannot be reached just now. Try again in a moment.";
  const https = (await headers()).get("x-forwarded-proto") === "https";
  (await cookies()).set(COOKIE, token, {
    httpOnly: true,
    sameSite: "strict",
    secure: https,
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  redirect("/desk/chat");
}

export async function signOut(): Promise<void> {
  (await cookies()).delete(COOKIE);
  redirect("/desk/chat");
}

/** Ask the Desk, in the session of the form or a new one. */
export async function ask(_: string | null, form: FormData): Promise<string | null> {
  const token = (await cookies()).get(COOKIE)?.value ?? process.env.LIGHTHOUSE_TOKEN;
  if (!token) return "Sign in first.";
  const text = String(form.get("text") ?? "").trim();
  if (!text) return "Ask something.";
  if (text.length > 4000) return "Ask in at most 4,000 characters.";
  const given = String(form.get("session") ?? "");
  const session = SESSION.test(given) ? given : crypto.randomUUID();
  const model = String(form.get("model") ?? "");
  const answer = await desk<Answer>("/api/desk/ask", token, { session, text, ...(model ? { model } : {}) });
  if (!answer.ok) {
    if (answer.status === 401) return "The desk no longer knows your token: sign in again.";
    if (answer.status === 400) return "That model is unavailable. Choose another model and try again.";
    if (answer.status === 422) return "Ask in plain words, in at most 4,000 characters.";
    return "The desk agent could not answer just now. Try again in a moment.";
  }
  redirect(`/desk/chat?session=${session}${model ? `&model=${encodeURIComponent(model)}` : ""}`);
}
