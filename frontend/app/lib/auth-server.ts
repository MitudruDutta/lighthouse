import "server-only";
export const AUTH_API =
  (process.env.LIGHTHOUSE_API ?? "http://127.0.0.1:8100") + "/api/auth";
export function sameOrigin(request: Request) {
  try {
    const origin = request.headers.get("origin");
    return !!origin && new URL(origin).host === request.headers.get("host");
  } catch {
    return false;
  }
}
