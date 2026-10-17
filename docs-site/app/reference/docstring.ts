// A docstring of the package as blocks a page can show. Docstrings are plain text: prose
// wrapped at about 90 characters, and tables of names and what they mean whose columns
// are lined up with spaces. Prose flows as paragraphs; a table keeps its columns.

export type Block = { kind: "text" | "table"; text: string };

/** Lined up with spaces: indented, or two spaces or more between words. */
function aligned(line: string): boolean {
  return /^\s+\S/.test(line) || /\S {2,}\S/.test(line);
}

/** The lines without the indentation they all share. */
function dedent(lines: string[]): string {
  const indents = lines.filter((l) => l.trim()).map((l) => l.match(/^ */)![0].length);
  const common = Math.min(...indents);
  return lines.map((l) => l.slice(common)).join("\n");
}

export function docBlocks(doc: string): Block[] {
  const blocks: Block[] = [];
  for (const paragraph of doc.trim().split(/\n\s*\n/)) {
    const lines = paragraph.split("\n");
    const table = lines.map(aligned);
    // The longest name of a table leaves one space before its meaning: still a row, when
    // its meaning starts in the column of the meanings above it.
    let column = -1;
    lines.forEach((line, i) => {
      const gap = line.match(/^\s*\S+ {2,}/);
      if (table[i] && gap) column = gap[0].length;
      else if (!table[i] && i > 0 && table[i - 1] && line.match(/^\s*\S+ /)?.[0].length === column)
        table[i] = true;
      else if (!table[i]) column = -1;
    });
    let run: string[] = [];
    let kind: Block["kind"] | null = null;
    const close = () => {
      if (!kind || !run.length) return;
      blocks.push({ kind, text: kind === "table" ? dedent(run) : run.map((l) => l.trim()).join(" ") });
      run = [];
    };
    lines.forEach((line, i) => {
      const now = table[i] ? "table" : "text";
      if (now !== kind) close();
      kind = now;
      run.push(line);
    });
    close();
  }
  return blocks;
}

/** Text with its `code` spans apart, for a page to mark them. */
export function codeSpans(text: string): { code: boolean; text: string }[] {
  return text
    .split(/(`[^`]+`)/)
    .filter(Boolean)
    .map((part) =>
      part.startsWith("`") && part.endsWith("`") && part.length > 2
        ? { code: true, text: part.slice(1, -1) }
        : { code: false, text: part },
    );
}
