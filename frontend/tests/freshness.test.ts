import assert from "node:assert/strict";
import test from "node:test";
import { failedSince, isFresh, rejectedWrites, utcTime } from "../app/lib/freshness";

test("zone-less API times use UTC and stale or invalid timestamps never read as connected", () => {
  assert.equal(utcTime("2026-10-15T12:00:00"), utcTime("2026-10-15T12:00:00Z"));
  assert.equal(isFresh("2026-10-15T11:55:00", "2026-10-15T12:00:00Z", 15), true);
  for (const at of [undefined, "invalid", "2026-10-15T11:45:00", "2026-10-15T12:02:00Z"]) {
    assert.equal(isFresh(at, "2026-10-15T12:00:00Z", 15), false);
  }
});

test("receipt health counts refused writes without counting accepted history updates", () => {
  assert.equal(rejectedWrites({ created: 10, changed: 3, inserted: 2, unchanged: 40, failed: 2, invalid: 1, conflict: 1, stale: 1 }), 5);
  assert.equal(rejectedWrites(), 0);
});

test("a successful retry clears a previously reported source failure", () => {
  const failure = { at: "2026-10-15T12:00:00" };
  assert.equal(failedSince(failure), true);
  assert.equal(failedSince(failure, { at: "2026-10-15T11:55:00" }), true);
  assert.equal(failedSince(failure, { at: "2026-10-15T12:05:00" }), false);
  assert.equal(failedSince(undefined), false);
});
