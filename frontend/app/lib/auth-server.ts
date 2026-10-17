import "server-only";
export const AUTH_API =
  (process.env.LIGHTHOUSE_API ?? "http://127.0.0.1:8100") + "/api/auth";
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
  try {
    const origin = request.headers.get("origin");
    return !!origin && new URL(origin).host === request.headers.get("host");
  } catch {
    return false;
  }
}
