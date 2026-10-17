import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { Suspense } from "react";
import { MessagesSquare, Plus, Sparkles } from "lucide-react";

import { Card, Loading, Prose, RefLink, Trace, When } from "@/app/components/ui";
import { DESK_COOKIE, type Message, type ModelChoice, type Session, desk } from "@/app/lib/api";
import { Ask } from "../forms";

export const metadata: Metadata = { title: "Ask the desk" };

export default function ChatPage(props: PageProps<"/desk/chat">) {
  return (
    <Suspense fallback={<Loading what="your sessions" />}>
      <Body {...props} />
    </Suspense>
  );
}

async function Body({ searchParams }: PageProps<"/desk/chat">) {
  const token = (await cookies()).get(DESK_COOKIE)?.value;
  const params = await searchParams;
  const asked = params.session;
  const current = typeof asked === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(asked) ? asked : undefined;
  if (!token)
    return (
      <Card title="Your conversations">
        <p>Sign in to ask the Desk and return to your saved conversations.</p>
        <Link href="/login" className="ops-primary mt-4">
          Sign in →
        </Link>
      </Card>
    );
  const [mine, said, choices] = await Promise.all([
    desk<Session[]>("/api/desk/sessions", token),
    current ? desk<Message[]>(`/api/desk/sessions/${current}`, token) : null,
    desk<ModelChoice[]>("/api/desk/models", token),
  ]);
  if (!mine.ok) {
    return (
      <Card title="Sign in again">
        <p className="mb-3 text-sm text-muted">
          {mine.status === 401 ? "Your session has ended." : "The desk cannot be reached just now."}
        </p>
        <Link href="/login" className="ops-primary">
          Sign in →
        </Link>
      </Card>
    );
  }
  const shown = said && said.ok ? said.data : [];
  const models = choices.ok ? choices.data : [];
  const selected =
    typeof params.model === "string" && models.some((choice) => choice.id === params.model)
      ? params.model
      : models[0]?.id;
  const model = models.find((choice) => choice.id === selected);
  return (
    <div className="desk-chat">
      <header className="desk-chat-head">
        <div>
          <p className="ops-kicker">Intelligence / Ask the desk</p>
          <h1>Ask the desk</h1>
          <p>
            Answers come from the graph, with the records the Desk read. Your sessions stay in your
            company&apos;s own graph.
          </p>
        </div>
        <div className="desk-chat-actions">
          <span className="desk-status" data-ready={models.length > 0 || undefined}>
            <i />
            {model ? model.model : choices.ok ? "No model set up" : "Assistant unavailable"}
          </span>
          <Link href="/desk/chat" className="ops-outline">
            <Plus size={16} />
            New session
          </Link>
        </div>
      </header>
      <div className="desk-chat-body">
        <aside className="desk-sessions" aria-label="Your sessions">
          <h2>
            <MessagesSquare size={15} /> Sessions
          </h2>
          {mine.data.length ? (
            <ul>
              {mine.data.map((s) => (
                <li key={s.id}>
                  <Link href={`/desk/chat?session=${s.id}`} aria-current={s.id === current ? "page" : undefined}>
                    <When at={s.active_at ?? s.opened_at} />
                    <small>
                      {s.messages} message{s.messages === 1 ? "" : "s"}
                    </small>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p>Your sessions appear here after your first question.</p>
          )}
        </aside>
        <section className="desk-thread" aria-label={current ? "This session" : "A new session"}>
          {shown.length === 0 ? (
            <div className="desk-welcome">
              <span className="desk-mark">
                <Sparkles size={22} />
              </span>
              <h2>What do you want to know?</h2>
              <p>
                The Desk reads the live berth board, the ports of the world, past cases, and what was
                learned, then answers with the records it used.
              </p>
            </div>
          ) : (
            <ol className="desk-messages">
              {shown.map((m) => (
                <li key={m.seq} data-role={m.role === "user" ? "user" : "desk"}>
                  {m.role === "user" ? (
                    <p className="desk-bubble desk-bubble-user">{m.text}</p>
                  ) : (
                    <div className="desk-answer">
                      <span className="desk-mark desk-mark-small" aria-hidden>
                        <Sparkles size={14} />
                      </span>
                      <div className="desk-bubble">
                        <Prose text={m.text} />
                        {m.mentions.length ? (
                          <p className="desk-read">
                            <span>Read</span>
                            {m.mentions.map((r) => (
                              <RefLink key={`${r[0]}${r[1]}`} refer={r} />
                            ))}
                          </p>
                        ) : null}
                        <Trace found={m} />
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
          <Ask
            key={selected}
            session={current}
            fresh={shown.length === 0}
            models={models}
            selected={selected}
            unavailable={!choices.ok}
          />
        </section>
      </div>
    </div>
  );
}
