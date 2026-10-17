import assert from "node:assert/strict";
import test from "node:test";
import reference from "../app/reference.json";
import { codeSpans, docBlocks } from "../app/reference/docstring";

const doc = (name: string) =>
  reference.sections.flatMap((s) => s.names).find((n) => n.name === name)!.doc;

test("a table keeps its columns, its longest name and its wrapped lines included", () => {
  const blocks = docBlocks(doc("Kind"));
  assert.deepEqual(blocks.map((b) => b.kind), ["text", "table", "text"]);
  const rows = blocks[1].text.split("\n");
  assert.equal(rows[0], "label      node label");
  assert.ok(rows.some((row) => row.startsWith("           Use SELF")));
  assert.ok(rows.at(-1)!.startsWith("dimensions size of the vectors"));
});

test("prose around a table flows, and an indented table loses its shared indent", () => {
  const blocks = docBlocks(doc("open_episode"));
  assert.deepEqual(blocks.map((b) => b.kind), ["text", "text", "table", "text"]);
  assert.equal(blocks[1].text, 'Returns a receipt {"id", "status"} with status');
  assert.ok(blocks[2].text.startsWith("opened   the episode was made"));
  assert.ok(docBlocks(doc("promote"))[0].text.includes("write what that adds up to."));
});

test("every docstring of the package becomes blocks without losing a word", () => {
  for (const name of reference.sections.flatMap((s) => s.names)) {
    const words = (t: string) => t.split(/\s+/).filter(Boolean);
    assert.deepEqual(words(docBlocks(name.doc).map((b) => b.text).join(" ")), words(name.doc), name.name);
  }
});

test("code spans", () => {
  assert.deepEqual(codeSpans("lists `about` and `at`."), [
    { code: false, text: "lists " },
    { code: true, text: "about" },
    { code: false, text: " and " },
    { code: true, text: "at" },
    { code: false, text: "." },
  ]);
  assert.deepEqual(codeSpans("a `` b"), [{ code: false, text: "a `` b" }]);
});
