// The pages that answer a search, best first. Every word must be on the page; a page whose
// title has the words comes before one that only mentions them, and then the page that
// uses them most.

export type Page = { path: string; title: string; text: string };

function count(text: string, word: string): number {
  let n = 0;
  for (let at = text.indexOf(word); at !== -1; at = text.indexOf(word, at + word.length)) n++;
  return n;
}

export function rank(pages: Page[], query: string, limit = 15): Page[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  return pages
    .map((page) => {
      const title = page.title.toLowerCase();
      const text = page.text.toLowerCase();
      if (!words.every((word) => title.includes(word) || text.includes(word))) return null;
      const inTitle = words.filter((word) => title.includes(word)).length;
      const uses = words.reduce((sum, word) => sum + count(text, word), 0);
      return { page, score: (inTitle === words.length ? 1000 : 0) + inTitle * 100 + uses };
    })
    .filter((hit): hit is { page: Page; score: number } => hit !== null)
    .sort((a, b) => b.score - a.score || a.page.title.localeCompare(b.page.title))
    .slice(0, limit)
    .map((hit) => hit.page);
}
