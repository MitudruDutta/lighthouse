// How the screen says what the agents did: in words, never as code or as an error.

export const AGENT_NAMES: Record<string, string> = {
  watcher: "Watcher",
  "port-watcher": "Port Watcher",
  reviewer: "Reviewer",
  desk: "Desk agent",
  digitraffic: "Arrivals feed",
  portwatch: "PortWatch",
};

/** What a model wrote in Markdown, as plain words for a short preview: without code
 * marks, emphasis, list bullets, or heading marks, with one space between words. The
 * underscores of names such as `port_days` stay. */
export function plain(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/^\s{0,3}(?:[*+-]|\d+\.|#{1,6})\s+/gm, "")
    .replace(/\*(\S[^*]*?)\*/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

export type Block =
  | { kind: "p" | "h"; text: string }
  | { kind: "ul" | "ol"; items: string[] }
  | { kind: "code"; text: string };

/** What a model wrote in Markdown, as blocks to show: paragraphs, headings, bulleted and
 * numbered lists, and fenced code. Inline marks stay in the text for the line to render. */
export function blocks(text: string): Block[] {
  const found: Block[] = [];
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  for (let n = 0; n < lines.length; n++) {
    const line = lines[n];
    if (/^\s*```/.test(line)) {
      const code: string[] = [];
      while (++n < lines.length && !/^\s*```/.test(lines[n])) code.push(lines[n]);
      found.push({ kind: "code", text: code.join("\n") });
      continue;
    }
    const bullet = line.match(/^\s{0,3}[*+\-•]\s+(.*)$/);
    const number = line.match(/^\s{0,3}\d+[.)]\s+(.*)$/);
    const heading = line.match(/^\s{0,3}#{1,6}\s+(.*)$/);
    const last = found.at(-1);
    if (bullet || number) {
      const kind = bullet ? "ul" : "ol";
      const item = (bullet ?? number)![1];
      if (last && last.kind === kind) last.items.push(item);
      else found.push({ kind, items: [item] });
    } else if (heading) found.push({ kind: "h", text: heading[1] });
    else if (!line.trim()) continue;
    else if (last && last.kind === "p" && lines[n - 1]?.trim()) last.text += "\n" + line;
    else found.push({ kind: "p", text: line });
  }
  return found;
}

/** At most `most` characters, cut between words, with an ellipsis when it was cut. */
export function excerpt(text: string, most: number): string {
  if (text.length <= most) return text;
  const cut = text.slice(0, most - 1);
  const space = cut.lastIndexOf(" ");
  const kept = space > most * 0.6 ? cut.slice(0, space) : cut;
  return `${kept.replace(/[\s,;:.–-]+$/, "")}…`;
}

// What the arrivals feed writes for a name it does not know: "not known", in Finnish.
const UNNAMED = new Set(["ei tiedossa", "unknown"]);

/** A name from the feed, or undefined when the feed only says it does not know one. */
export function known(name: string | null | undefined): string | undefined {
  return name && !UNNAMED.has(name.trim().toLowerCase()) ? name : undefined;
}

export function agentName(by: string | undefined): string {
  return (by && AGENT_NAMES[by]) ?? by ?? "An agent";
}

/** A tool call as the Desk keeps it, `look(kind=Berth, key=FIHEL/VUOS/VC2)`, in words. */
export function describeTool(call: string): string {
  const match = /^(\w+)\(([\s\S]*)\)$/.exec(call);
  if (!match) return call;
  const [, name, inside] = match;
  const args: Record<string, string> = {};
  for (const part of inside.split(/, (?=\w+=)/)) {
    const at = part.indexOf("=");
    if (at > 0) args[part.slice(0, at)] = part.slice(at + 1);
  }
  const thing = `${(args.kind ?? "").toLowerCase().replace("portcall", "port call")} ${args.key ?? ""}`.trim();
  switch (name) {
    case "find":
      return `Searched ${(args.kind ?? "").toLowerCase()}s for “${args.words ?? ""}”`;
    case "look":
      return `Looked up ${thing}`;
    case "versions":
      return `Read the history of ${thing}`;
    case "pointing":
      return `Listed what points at ${args.key ?? "it"}`;
    case "alike":
      return `Found what is like ${thing}`;
    case "connected":
      return `Traced how ${args.from_key ?? "one"} connects to ${args.to_key ?? "the other"}`;
    case "central":
      return "Ranked by how much points at each";
    case "incidents":
      return "Grouped episodes that belong together";
    case "overloaded":
      return "Checked which berths are overloaded";
    case "episode":
      return "Read the episode";
    case "episodes_about":
      return `Read past episodes about ${args.key ?? "it"}`;
    case "lessons_about":
      return `Recalled what was learned about ${args.key ?? "it"}`;
    case "playbooks_for":
      return "Looked for a playbook that fits";
    case "unusual_ports":
      return "Listed the ports unusual now";
    case "port_days":
      return `Read the days of port ${args.key ?? ""}`.trim();
    case "busiest_ports":
      return args.country ? `Ranked the busiest ports of ${args.country}` : "Ranked the busiest ports";
    case "note":
      return "Wrote a note into the episode";
    case "raise_task":
      return "Raised a task";
    case "hand_over":
      return `Handed work to ${args.to ?? "another agent"}`;
    default:
      return name.replaceAll("_", " ");
  }
}

type Entry = { type?: string; by?: string; [value: string]: unknown };

/** One entry of an episode, as one sentence. */
export function said(entry: Entry): string {
  const name = String(entry.name ?? entry.port ?? entry.berth ?? "");
  const number = (v: unknown) => (typeof v === "number" ? v.toLocaleString("en", { maximumFractionDigits: 1 }) : "?");
  switch (entry.type) {
    case "observation":
      if (entry.situation === "port-activity") {
        return `${name} is ${String(entry.state)}: ${number(entry.calls)} port calls against a usual ${number(entry.usual)}`;
      }
      if (entry.situation === "berth-overload") {
        return `Berth ${name}: ${number(entry.expected)} ships expected at once, it has held ${number(entry.capacity)}`;
      }
      return "Saw something unusual";
    case "recall":
      return `Recalled: ${String(entry.statement ?? "a lesson")}`;
    case "action":
      return entry.to ? `Raised a task and handed the episode to the ${agentName(String(entry.to)).toLowerCase()}` : String(entry.did ?? "Acted");
    case "assessment": {
      const text = plain(String(entry.text ?? ""));
      return excerpt(text.split(/(?<=[.!?])\s/)[0] ?? text, 160);
    }
    case "outcome":
      if (entry.back_to_usual) return `Back to usual after ${number(entry.days)} day${entry.days === 1 ? "" : "s"}`;
      if (entry.held !== undefined) return entry.held ? "Ended: the berth took them all" : "Ended: the berth could not take them all";
      return "The episode ended";
    default:
      return String(entry.type ?? "Wrote an entry");
  }
}
