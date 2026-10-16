import "server-only";
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

export function googleFlow(
  api: string,
  sessionCookie: string,
  origin: string,
  profile: string,
) {
  const base = origin.replace(/\/$/, "");
  const callbackUri = base + "/api/auth/google/callback";
  const flowCookie = sessionCookie + "_google";
  const secure = base.startsWith("https:");
  function failure(reason = "failed") {
    const response = NextResponse.redirect(
      base + "/login?google=" + reason,
      303,
    );
    response.cookies.set(flowCookie, "", {
      path: "/api/auth/google",
      maxAge: 0,
      httpOnly: true,
      secure,
      sameSite: "lax",
    });
    response.headers.set("Cache-Control", "no-store");
    response.headers.set("Referrer-Policy", "no-referrer");
    return response;
  }
  async function start(request: NextRequest) {
    if (request.headers.get("host") !== new URL(base).host) return failure();
    const link = request.nextUrl.searchParams.get("link") === "1";
    const session = link
      ? request.cookies.get(sessionCookie)?.value
      : undefined;
    if (link && !session?.startsWith("lhs_")) return failure();
    const state = randomBytes(32).toString("base64url");
    const nonce = randomBytes(32).toString("base64url");
    const verifier = randomBytes(32).toString("base64url");
    const challenge = createHash("sha256").update(verifier).digest("base64url");
    try {
      const result = await fetch(api + "/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          redirect_uri: callbackUri,
          state,
          nonce,
          challenge,
        }),
        cache: "no-store",
        signal: AbortSignal.timeout(15000),
      });
      if (!result.ok) return failure("unavailable");
      const data = await result.json();
      const target = new URL(data.url);
      if (target.origin !== "https://accounts.google.com") return failure();
      const response = NextResponse.redirect(target, 303);
      response.cookies.set(
        flowCookie,
        JSON.stringify({ state, nonce, verifier, link, session }),
        {
          httpOnly: true,
          secure,
          sameSite: "lax",
          path: "/api/auth/google",
          maxAge: 600,
        },
      );
      response.headers.set("Cache-Control", "no-store");
      response.headers.set("Referrer-Policy", "no-referrer");
      return response;
    } catch {
      return failure("unavailable");
    }
  }
  async function callback(request: NextRequest) {
    if (request.headers.get("host") !== new URL(base).host) return failure();
    try {
      const flow = JSON.parse(request.cookies.get(flowCookie)?.value ?? "{}");
      const state = request.nextUrl.searchParams.get("state") ?? "";
      if (
        typeof flow.state !== "string" ||
        state.length !== flow.state.length ||
        !timingSafeEqual(Buffer.from(state), Buffer.from(flow.state))
      )
        return failure();
      if (request.nextUrl.searchParams.has("error"))
        return failure("cancelled");
      const code = request.nextUrl.searchParams.get("code");
      if (!code || code.length > 4096) return failure();
      const result = await fetch(api + "/exchange", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(flow.link && flow.session
            ? { Authorization: `Bearer ${flow.session}` }
            : {}),
        },
        body: JSON.stringify({
          redirect_uri: callbackUri,
          code,
          nonce: flow.nonce,
          verifier: flow.verifier,
          link: flow.link === true,
        }),
        cache: "no-store",
        signal: AbortSignal.timeout(20000),
      });
      if (!result.ok)
        return failure(result.status === 409 ? "existing" : "failed");
      const data = await result.json();
      if (typeof data.token !== "string" || !data.token.startsWith("lhs_"))
        return failure();
      const response = NextResponse.redirect(
        base + (flow.link ? profile : "/dashboard"),
        303,
      );
      // Lax permits Google's top-level redirect; mutations still require the same origin.
      response.cookies.set(sessionCookie, data.token, {
        httpOnly: true,
        secure,
        sameSite: "lax",
        path: "/",
        maxAge: 604800,
      });
      response.cookies.set(flowCookie, "", {
        path: "/api/auth/google",
        maxAge: 0,
        httpOnly: true,
        secure,
        sameSite: "lax",
      });
      response.headers.set("Cache-Control", "no-store");
      response.headers.set("Referrer-Policy", "no-referrer");
      return response;
    } catch {
      return failure();
    }
  }
  return { start, callback };
}
