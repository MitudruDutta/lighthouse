import type { Metadata } from "next";

import reference from "../reference.json";

export const metadata: Metadata = { title: "Python API" };

const TITLES: Record<string, string> = {
  kinds: "Kinds",
  graphs: "Graphs and schema",
  write: "Writing",
  read: "Reading history",
  recall: "Recall",
  episodes: "Episodes",
  extraction: "Rows from entries",
  handoffs: "Handoffs",
  lessons: "Lessons",
  playbooks: "Playbooks",
  promotion: "Promotion",
  algorithms: "Graph algorithms",
  conversation: "Conversations",
  tasks: "Tasks",
  clock: "Time",
};

/** Every public name of the package, as the package itself describes it. */
export default function Reference() {
  return (
    <>
      <h1 className="serif mb-3 text-4xl leading-tight">Python API</h1>
      <p className="my-3 leading-relaxed">
        Every public name of <code>lighthouse</code>, grouped by what it is for,
        with its signature and its docstring. This page is read from the
        package: <code>scripts/reference.py</code> writes it, and a test of the
        package fails when it is not up to date.
      </p>
      <nav
        aria-label="Parts of the package"
        className="my-6 flex flex-wrap gap-2 text-sm"
      >
        {reference.sections.map((section) => (
          <a
            key={section.part}
            href={`#${section.part}`}
            className="button-quiet !py-1 !font-normal"
          >
            {TITLES[section.part] ?? section.part}
          </a>
        ))}
      </nav>
      {reference.sections.map((section) => (
        <section key={section.part} aria-labelledby={section.part}>
          <h2
            id={section.part}
            className="serif mt-12 mb-2 scroll-mt-6 text-[26px] leading-snug"
          >
            {TITLES[section.part] ?? section.part}
          </h2>
          <p className="mb-5 text-muted">
            {section.about}{" "}
            <code className="text-[13px]">lighthouse.{section.part}</code>
          </p>
          <div className="grid gap-6">
            {section.names.map((item) => (
              <article
                key={item.name}
                id={item.name}
                className="scroll-mt-6 border-l-2 pl-4"
                style={{ borderColor: "var(--rule)" }}
              >
                <h3 className="font-mono text-[15px] font-semibold break-words">
                  {item.name}
                  <span className="font-normal text-muted">
                    {item.signature}
                  </span>
                </h3>
                <p className="mt-1.5 text-[15px] leading-relaxed whitespace-pre-wrap">
                  {item.doc}
                </p>
              </article>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
