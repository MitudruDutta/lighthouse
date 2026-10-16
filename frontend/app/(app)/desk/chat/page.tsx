import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { Suspense } from "react";

import { Card, Loading, Prose, RefLink, Trace, When } from "@/app/components/ui";
import { DESK_COOKIE, type Message, type ModelChoice, type Session, desk } from "@/app/lib/api";
import { signOut } from "../actions";
import { Ask } from "../forms";

export const metadata: Metadata = { title: "Ask the desk" };

export default function ChatPage(props: PageProps<"/desk/chat">) {
  return (
    <div className="grid gap-5">
      <div>
        <h1 className="serif text-3xl">Ask the desk</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          The Desk answers from the graph, with the tools it picks, and says which. Your sessions are kept in your
          company&apos;s own graph, with a summary of long ones; what you asked before, in other sessions, is given to
          it when it fits.
        </p>
      </div>
      <Suspense fallback={<Loading what="your sessions" />}>
        <Body {...props} />
      </Suspense>
    </div>
  );
}

async function Body({ searchParams }: PageProps<"/desk/chat">) {
  const own = (await cookies()).get(DESK_COOKIE)?.value;
  const token = own;
  const params = await searchParams;
  const asked = params.session;
  const current = typeof asked === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(asked) ? asked : undefined;
  if (!token) return <Card title="Your conversations"><p>Sign in to ask the Desk and return to your saved conversations.</p><Link href="/login" className="ops-primary mt-4">Sign in →</Link></Card>;
  const [mine, said, choices] = await Promise.all([
    desk<Session[]>("/api/desk/sessions", token),
    current ? desk<Message[]>(`/api/desk/sessions/${current}`, token) : null,
    desk<ModelChoice[]>("/api/desk/models", token),
  ]);
  if (!mine.ok) {
    return (
      <Card title="Sign in again">
        <p className="mb-3 text-sm text-muted">{mine.status === 401 ? "The desk no longer knows your token." : "The desk cannot be reached just now."}</p>
        <Link href="/login" className="ops-primary">Sign in →</Link>
      </Card>
    );
  }
  const shown = said && said.ok ? said.data : [];
  const models = choices.ok ? choices.data : [];
  const selected = typeof params.model === "string" && models.some(choice => choice.id === params.model) ? params.model : models[0]?.id;
  return (
    <div className="grid gap-5 md:grid-cols-[240px_1fr]">
      <Card title="Your sessions">
        <ul className="grid gap-1 text-sm">
          <li>
            <Link href="/desk/chat" className={current ? "link" : "font-semibold"}>
              + A new session
            </Link>
          </li>
          {mine.data.map((s) => (
            <li key={s.id}>
              <Link href={`/desk/chat?session=${s.id}`} className={s.id === current ? "font-semibold" : "link"}>
                <When at={s.active_at ?? s.opened_at} />
              </Link>
              <span className="text-xs text-faint"> · {s.messages}</span>
            </li>
          ))}
        </ul>
        {own ? (
        <form action={signOut} className="mt-4">
          <button type="submit" className="!bg-transparent !p-0 text-xs !font-normal text-faint underline">
            Sign out
          </button>
        </form>
        ) : null}
      </Card>
      <Card title={current ? "This session" : "A new session"}>
        {shown.length === 0 ? <p className="mb-3 text-sm text-muted">Ask in your own words, or start from one of these.</p> : null}
        <ol className="mb-4 grid gap-4">
          {shown.map((m) => (
            <li
              key={m.seq}
              className={m.role === "user" ? "ml-auto max-w-[85%] rounded-lg p-3" : "max-w-[95%]"}
              style={m.role === "user" ? { background: "var(--info-bg)" } : undefined}
            >
              {m.role === "user" ? <p className="whitespace-pre-wrap text-sm">{m.text}</p> : <Prose text={m.text} />}
              {m.role === "assistant" ? <Trace found={m} /> : null}
              {m.mentions.length ? (
                <p className="mt-1 flex flex-wrap gap-2 text-xs">
                  <span className="text-faint">Read:</span>
                  {m.mentions.map((r) => (
                    <RefLink key={`${r[0]}${r[1]}`} refer={r} />
                  ))}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
        <Ask key={selected} session={current} fresh={shown.length === 0} models={models} selected={selected} />
      </Card>
    </div>
  );
}
