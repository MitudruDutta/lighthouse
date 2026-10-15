import { Suspense } from "react";

import { Badge, Card, Loading, RefLink, When, headline } from "../../components/ui";
import { type Entry, type Episode, api, segments } from "../../lib/api";

const OWN = new Set(["id", "seq", "type", "at", "recorded_at", "by", "cites"]);

export default function EpisodePage(props: PageProps<"/episodes/[...id]">) {
  return (
    <Suspense fallback={<Loading what="the episode" />}>
      <Body {...props} />
    </Suspense>
  );
}

function show(value: unknown): string {
  if (Array.isArray(value)) return value.map(show).join(", ");
  if (typeof value === "number") return value.toLocaleString("en", { maximumFractionDigits: 2 });
  return String(value);
}

function Values({ entry }: { entry: Entry }) {
  const values = Object.entries(entry).filter(([name, value]) => !OWN.has(name) && value !== null && value !== undefined);
  if (values.length === 0) return null;
  return (
    <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
      {values.map(([name, value]) => (
        <div key={name} className="contents">
          <dt className="text-muted">{name.replaceAll("_", " ")}</dt>
          <dd className="break-words">{show(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

async function Body({ params }: PageProps<"/episodes/[...id]">) {
  const id = (await params).id.map(decodeURIComponent).join("/");
  const episode = await api<Episode>(`/api/episodes/${segments(id)}`);
  return (
    <div className="grid gap-5">
      <div>
        <h1 className="break-words text-xl font-semibold tracking-tight">{headline(id, episode.entries[0])}</h1>
        <p className="mt-1 break-words font-mono text-xs text-faint">{id}</p>
        <p className="mt-1 text-sm text-muted">
          Opened <When at={episode.opened_at} /> by {episode.by}
          {episode.closed_at ? (
            <>
              {" "}
              · closed <When at={episode.closed_at} />
            </>
          ) : (
            <> · open</>
          )}
        </p>
        <p className="mt-2 flex flex-wrap gap-2 text-sm">
          <span className="text-muted">About:</span>
          {episode.about.map((r) => (
            <RefLink key={`${r[0]}${r[1]}`} refer={r} />
          ))}
        </p>
      </div>
      <Card title="What happened, in order">
        <ol className="grid gap-4">
          {episode.entries.map((entry) => (
            <li key={entry.id} className="border-l-2 pl-4" style={{ borderColor: "var(--line)" }}>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-faint">#{entry.seq}</span>
                <Badge tone={entry.type}>{entry.type}</Badge>
                <When at={entry.at} />
                <span className="text-muted">by {entry.by}</span>
              </div>
              <Values entry={entry} />
              {entry.cites.length ? (
                <p className="mt-2 flex flex-wrap gap-2 text-xs">
                  <span className="text-faint">Evidence, as it was then:</span>
                  {entry.cites.slice(0, 20).map((r) => (
                    <RefLink key={`${r[0]}${r[1]}`} refer={r} />
                  ))}
                  {entry.cites.length > 20 ? <span className="text-faint">and {entry.cites.length - 20} more</span> : null}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
