export const DOCS_URL = (
  process.env.NEXT_PUBLIC_LIGHTHOUSE_DOCS_URL ?? "https://lighthouse-memory-docs.vercel.app"
).replace(/\/$/, "");
export function docs(path = ""): string {
  return `${DOCS_URL}${path}`;
}

export const MEMORY_URL = (
  process.env.NEXT_PUBLIC_LIGHTHOUSE_MEMORY_URL ?? "https://lighthouse-memory.vercel.app"
).replace(/\/$/, "");
