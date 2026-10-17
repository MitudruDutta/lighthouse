import assert from "node:assert/strict";
import test from "node:test";
import index from "../app/search-index.json";
import { rank } from "../components/search-rank";

test("a page with the words in its title comes first", () => {
  assert.equal(rank(index, "handoff")[0].title, "Tasks and handoffs");
  assert.equal(rank(index, "playbook")[0].title, "Lessons and playbooks");
  assert.equal(rank(index, "http api")[0].title, "Memory HTTP API");
});

test("every word must be on the page, and nothing is found for nothing", () => {
  assert.deepEqual(rank(index, ""), []);
  assert.deepEqual(rank(index, "handoff zzzunknownword"), []);
  const hits = rank(index, "vector");
  assert.ok(hits.length > 0 && hits.every((p) => `${p.title} ${p.text}`.toLowerCase().includes("vector")));
});
