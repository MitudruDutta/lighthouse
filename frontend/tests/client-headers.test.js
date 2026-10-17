import assert from "node:assert/strict";
import { mock, test } from "bun:test";
mock.module("server-only", () => ({}));
const implementations = [
  (await import("../app/lib/auth-server")).clientHeaders,
  (await import("../../memory-site/app/lib/server")).clientHeaders,
];
for (const [index, clientHeaders] of implementations.entries()) {
  test(`client headers ${index}: nearest hop, and only with the proxy token`, () => {
    const original = process.env.LIGHTHOUSE_PROXY_TOKEN;
    const request = (forwarded) =>
      new Request("https://app.example/api/auth/login", {
        headers: forwarded ? { "x-forwarded-for": forwarded } : {},
      });
    try {
      delete process.env.LIGHTHOUSE_PROXY_TOKEN;
      assert.deepEqual(clientHeaders(request("203.0.113.9")), {});
      process.env.LIGHTHOUSE_PROXY_TOKEN = "proxy-secret";
      assert.deepEqual(clientHeaders(request()), {});
      // A proxy appends the address it saw: what the browser wrote comes first.
      assert.deepEqual(clientHeaders(request("198.51.100.1, 203.0.113.9")), {
        "X-Lighthouse-Client": "203.0.113.9",
        "X-Lighthouse-Proxy": "proxy-secret",
      });
    } finally {
      if (original === undefined) delete process.env.LIGHTHOUSE_PROXY_TOKEN;
      else process.env.LIGHTHOUSE_PROXY_TOKEN = original;
    }
  });
}
