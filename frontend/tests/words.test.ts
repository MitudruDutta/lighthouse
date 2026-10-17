import assert from "node:assert/strict";
import test from "node:test";
import { excerpt, plain, said } from "../app/components/words";

test("plain: what a model wrote in Markdown reads as words", () => {
  const text =
    "**Situation:** A berth overload at `FIINK/IS/5`.\n* 3406955 (Vessel 8207379)\n* *Two* more\n## Impact\nUses `port_days` and episodes_about.";
  assert.equal(
    plain(text),
    "Situation: A berth overload at FIINK/IS/5. 3406955 (Vessel 8207379) Two more Impact Uses port_days and episodes_about.",
  );
  assert.equal(plain("```json\n{\"a\": 1}\n```\nDone."), "Done.");
});

test("excerpt: cut between words, with an ellipsis only when cut", () => {
  assert.equal(excerpt("short text", 20), "short text");
  assert.equal(excerpt("three port calls are scheduled for one berth", 30), "three port calls are…");
  assert.equal(excerpt("one, two, three, four, five, six", 17), "one, two, three…");
  assert.equal(excerpt("a".repeat(40), 10), "a".repeat(9) + "…");
  assert.ok(excerpt("word ".repeat(100), 185).length <= 185);
});

test("an assessment's first sentence is shown without Markdown", () => {
  assert.equal(
    said({ type: "assessment", text: "A berth overload at `FIINK/IS/5` (**high**). Then more." }),
    "A berth overload at FIINK/IS/5 (high).",
  );
});
