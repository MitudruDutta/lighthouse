import assert from "node:assert/strict";
import test from "node:test";
import { judged } from "../app/components/Bars";

test("a missing observation is not classified as a zero-call disruption", () => {
  const baseline = Array.from({ length: 14 }, (_, i) => ({ day: `2026-10-${String(i + 1).padStart(2, "0")}`, calls: 8 }));
  const missing = judged([...baseline, { day: "2026-10-15" }]).at(-1)!;
  assert.equal(missing.usual, 8);
  assert.equal(missing.unusual, false);
  const zero = judged([...baseline, { day: "2026-10-15", calls: 0 }]).at(-1)!;
  assert.equal(zero.unusual, true);
});
