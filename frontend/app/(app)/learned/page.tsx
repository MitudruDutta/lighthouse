import { Suspense } from "react";

import { Badge, Card, Empty, Loading, RefLink } from "@/app/components/ui";
import { type Lesson, type Playbook, api } from "@/app/lib/api";

export default function Learned() {
  return (
    <div className="grid gap-5">
      <div>
        <p className="eyebrow mb-3">Intelligence / Shared memory</p>
        <h1 className="display">Lessons & playbooks<span className="text-[var(--sky)]">.</span></h1>
        <p className="mt-1 text-sm text-muted">
          Lessons and playbooks rest on episodes that ended. The weight of a lesson is the episodes for it less those
          against it.
        </p>
      </div>
      <Suspense fallback={<Loading what="lessons" />}>
        <Lessons />
      </Suspense>
      <Suspense fallback={<Loading what="playbooks" />}>
        <Playbooks />
      </Suspense>
    </div>
  );
}

async function Lessons() {
  const lessons = await api<Lesson[]>("/api/lessons");
  return (
    <Card title="Lessons" aside={`${lessons.length}`}>
      {lessons.length === 0 ? (
        <Empty>No lesson yet.</Empty>
      ) : (
        <ul className="grid gap-3">
          {lessons.map((lesson) => (
            <li key={lesson.id} id={lesson.id} className="rounded-lg border border-[var(--edge)] p-4 text-sm">
              <div>
                <Badge tone="recall">{lesson.weight}</Badge> {lesson.statement}
              </div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-faint">
                <span>for: {lesson.supported_by?.length ?? 0}</span>
                <span>against: {lesson.contradicted_by?.length ?? 0}</span>
                {(lesson.about ?? []).map((r) => (
                  <RefLink key={`${r[0]}${r[1]}`} refer={r} />
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

async function Playbooks() {
  const books = await api<Playbook[]>("/api/playbooks");
  return (
    <Card title="Playbooks" aside={`${books.length}`}>
      {books.length === 0 ? (
        <Empty>No playbook yet: one is written when enough episodes show the same steps working.</Empty>
      ) : (
        <ul className="grid gap-3 text-sm">
          {books.map((book) => (
            <li key={book.id}>
              <div className="font-medium">
                {book.name} <span className="text-faint">v{book.version}</span>{" "}
                {book.enabled ? <Badge tone="closed">on</Badge> : <Badge>off</Badge>}
              </div>
              <div className="text-xs text-muted">
                when {Object.entries(book.trigger).map(([k, v]) => `${k} ${String(v)}`).join(", ")}
              </div>
              <ol className="ml-5 list-decimal text-sm">
                {book.steps.map((step, i) => (
                  <li key={i}>{Object.entries(step).map(([k, v]) => `${k} ${String(v)}`).join(", ")}</li>
                ))}
              </ol>
              <div className="text-xs text-faint">
                ran {book.runs ?? 0}, worked {book.succeeded ?? 0}, failed {book.failed ?? 0}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
