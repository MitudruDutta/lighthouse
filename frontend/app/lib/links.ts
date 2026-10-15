export const DOCS_URL = (process.env.NEXT_PUBLIC_LIGHTHOUSE_DOCS_URL ?? "http://localhost:3002").replace(/\/$/, "");
export function docs(path = ""): string { return `${DOCS_URL}${path}`; }
