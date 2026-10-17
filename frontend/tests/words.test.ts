import assert from "node:assert/strict";
import test from "node:test";
import { blocks, excerpt, known, plain, said } from "../app/components/words";

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

test("blocks: lists, headings, and paragraphs of a model's answer", () => {
  const text =
    "The berths that expect more ships:\n\n*   FIHKO/WEST/RR3 (Kotka)\n*   FIINK/IS/5\n\n## Next\n1. Check the **feed**\n2) Ask again\nA line\nand its next line.\n```\ncode * here\n```";
  assert.deepEqual(blocks(text), [
    { kind: "p", text: "The berths that expect more ships:" },
    { kind: "ul", items: ["FIHKO/WEST/RR3 (Kotka)", "FIINK/IS/5"] },
    { kind: "h", text: "Next" },
    { kind: "ol", items: ["Check the **feed**", "Ask again"] },
    { kind: "p", text: "A line\nand its next line." },
    { kind: "code", text: "code * here" },
  ]);
});

test("known: the feed's word for an unknown name is not a name", () => {
  assert.equal(known("Ei tiedossa"), undefined);
  assert.equal(known(" ei tiedossa "), undefined);
  assert.equal(known(null), undefined);
  assert.equal(known("Länsisatama"), "Länsisatama");
});
