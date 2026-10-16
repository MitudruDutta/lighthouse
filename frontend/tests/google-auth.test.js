import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mock, test } from "bun:test";
import { NextRequest } from "next/server";
mock.module("server-only", () => ({}));
const implementations = [
  (await import("../app/lib/google-server")).googleFlow,
  (await import("../../memory-site/app/lib/google-server")).googleFlow,
];
for (const [index, googleFlow] of implementations.entries()) {
  test(`Google flow ${index}: PKCE, state, cancellation, and secure session`, async () => {
    const original = globalThis.fetch;
    const flow = googleFlow(
      "https://api.example/auth/google",
      "session",
      "https://app.example",
      "/profile",
    );
    let starts = {};
    let exchanges = 0;
    globalThis.fetch = async (url, options) => {
      if (String(url).endsWith("/start")) {
        starts = JSON.parse(String(options?.body));
        return Response.json({
          url: "https://accounts.google.com/o/oauth2/v2/auth",
        });
      }
      exchanges++;
      const body = JSON.parse(String(options?.body));
      assert.equal(body.verifier, saved.verifier);
      assert.equal(body.nonce, saved.nonce);
      assert.equal(
        body.redirect_uri,
        "https://app.example/api/auth/google/callback",
      );
      return Response.json({ token: "lhs_private_session" });
    };
    let saved;
    try {
      const start = await flow.start(
        new NextRequest("https://app.example/api/auth/google", {
          headers: { host: "app.example" },
        }),
      );
      const cookie = start.cookies.get("session_google");
      saved = JSON.parse(cookie.value);
      assert.equal(start.status, 303);
      assert.equal(cookie.httpOnly, true);
      assert.equal(cookie.sameSite, "lax");
      assert.equal(cookie.secure, true);
      assert.equal(cookie.maxAge, 600);
      assert.equal(starts.state, saved.state);
      assert.equal(starts.nonce, saved.nonce);
      assert.equal(
        starts.challenge,
        createHash("sha256").update(saved.verifier).digest("base64url"),
      );
      const headers = {
        host: "app.example",
        cookie: `session_google=${encodeURIComponent(cookie.value)}`,
      };
      const rejected = await flow.callback(
        new NextRequest(
          "https://app.example/api/auth/google/callback?state=wrong&code=bad",
          { headers },
        ),
      );
      assert.match(rejected.headers.get("location"), /google=failed$/);
      assert.equal(exchanges, 0);
      const cancelled = await flow.callback(
        new NextRequest(
          `https://app.example/api/auth/google/callback?state=${saved.state}&error=access_denied`,
          { headers },
        ),
      );
      assert.match(cancelled.headers.get("location"), /google=cancelled$/);
      assert.equal(cancelled.cookies.get("session_google")?.maxAge, 0);
      assert.equal(
        cancelled.cookies.get("session_google")?.path,
        "/api/auth/google",
      );
      const accepted = await flow.callback(
        new NextRequest(
          `https://app.example/api/auth/google/callback?state=${saved.state}&code=one-use-code`,
          { headers },
        ),
      );
      assert.equal(exchanges, 1);
      assert.equal(
        accepted.headers.get("location"),
        "https://app.example/dashboard",
      );
      assert.equal(accepted.cookies.get("session")?.httpOnly, true);
      assert.equal(accepted.cookies.get("session")?.secure, true);
      assert.equal(accepted.cookies.get("session_google")?.maxAge, 0);
      assert.equal(accepted.headers.get("cache-control"), "no-store");
      assert.equal(accepted.headers.get("referrer-policy"), "no-referrer");
    } finally {
      globalThis.fetch = original;
    }
  });
}
