import { Suspense } from "react";
import Link from "next/link";

import { Badge, Card, Loading, Prose, RefLink, Trace, When, headline } from "@/app/components/ui";
import { type Checked, type Entry, type Episode, api, segments } from "@/app/lib/api";

const OWN = new Set(["id", "seq", "type", "at", "recorded_at", "by", "cites"]);
// Shown by Trace, for an entry that a model wrote.
const TRACED = new Set(["model", "outcome", "unsupported", "tools", "tool_rows", "tool_ms"]);

export default function EpisodePage(props: PageProps<"/episodes/[...id]">) {
  return (
    <Suspense fallback={<Loading what="the episode" />}>
      <Body {...props} />
    </Suspense>
  );
}

const PORT_CALLS = new Set(["calls", "together"]);
const TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

function Shown({ name, value }: { name: string; value: unknown }) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-faint">none</span>;
    if (PORT_CALLS.has(name)) {
      return (
        <span className="flex flex-wrap gap-x-2">
          {value.map((id) => (
            <RefLink key={String(id)} refer={["PortCall", id as number]}>
              {String(id)}
            </RefLink>
          ))}
        </span>
      );
    }
    return <>{value.map(String).join(", ")}</>;
  }
  if (typeof value === "string" && TIME.test(value)) return <When at={value} />;
  if (typeof value === "number") {
    return <>{Number.isInteger(value) ? String(value) : value.toLocaleString("en", { maximumFractionDigits: 2 })}</>;
  }
  if (typeof value === "boolean") return <>{value ? "yes" : "no"}</>;
  if (name === "text" && typeof value === "string") return <Prose text={value} />;
  return <>{String(value)}</>;
}

function Values({ entry }: { entry: Entry }) {
  const traced = entry.outcome !== undefined;
  const values = Object.entries(entry).filter(
    ([name, value]) => !OWN.has(name) && !(traced && TRACED.has(name)) && value !== null && value !== undefined,
  );
  if (values.length === 0) return null;
  return (
    <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
      {values.map(([name, value]) => (
        <div key={name} className="contents">
          <dt className="text-muted">{name.replaceAll("_", " ")}</dt>
          <dd className="min-w-0 break-words">
            <Shown name={name} value={value} />
          </dd>
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
        <h1 className="serif break-words text-3xl">{headline(id, episode.entries[0])}</h1>
        <p className="mt-1 break-words font-mono text-xs text-faint">{id}</p>
        <Link href={`/investigate?kind=Episode&key=${encodeURIComponent(id)}`} className="button-quiet mt-3 !text-xs">Explore connected evidence ↗</Link>
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
              {entry.outcome !== undefined ? <Trace found={entry as Checked} /> : null}
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
