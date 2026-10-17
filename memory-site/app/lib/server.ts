import "server-only";
export const API = process.env.MEMORY_API ?? "http://127.0.0.1:8200";
export const COOKIE = "lighthouse_memory_session";
export const DOCS =
  process.env.NEXT_PUBLIC_MEMORY_DOCS_URL ?? "http://localhost:3002";
export async function request(
  path: string,
  token?: string,
  method = "GET",
  body?: unknown,
) {
  try {
    const response = await fetch(API + path, {
      method,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    return { status: response.status, data: await response.json() };
  } catch {
    return {
      status: 503,
      data: {
        detail:
          "This service is temporarily unavailable. Please try again shortly.",
      },
    };
  }
}
// The API limits sign-in attempts per browser, and sees only this server. Pass on the
// address Next.js was given, nearest hop last, with the token that proves it came from here.
export function clientHeaders(request: Request): Record<string, string> {
  const token = process.env.LIGHTHOUSE_PROXY_TOKEN;
  const address = request.headers
    .get("x-forwarded-for")
    ?.split(",")
    .at(-1)
    ?.trim();
  return token && address
    ? { "X-Lighthouse-Client": address, "X-Lighthouse-Proxy": token }
    : {};
}
export function sameOrigin(request: Request) {
  const origin = request.headers.get("origin");
  try {
    return !!origin && new URL(origin).host === request.headers.get("host");
  } catch {
    return false;
  }
}
