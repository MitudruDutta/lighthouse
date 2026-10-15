import assert from "node:assert/strict";
import test from "node:test";
import type { GraphNode } from "../app/lib/api";
import { nodeTitle, refTitle } from "../app/lib/investigation";

const episode: GraphNode = { id: 1, ref: ["Episode", "berth-overload:FIHEL/VUOS/VC2:2026-10-15T12:00:00"], title: "berth-overload:FIHEL/VUOS/VC2:2026-10-15T12:00:00", state: "open" };
test("inspector headings stay readable without changing exact record identifiers", () => {
  assert.equal(nodeTitle(episode), "Berth overlap");
  assert.equal(nodeTitle({ ...episode, title: "A named investigation" }), "A named investigation");
  assert.equal(episode.ref[1], "berth-overload:FIHEL/VUOS/VC2:2026-10-15T12:00:00");
});
test("path labels match numeric and string keys while preserving unknown references", () => {
  const call: GraphNode = { id: 2, ref: ["PortCall", 42], title: "42", state: null };
  assert.equal(refTitle(["PortCall", "42"], [call]), "Port call 42");
  assert.equal(refTitle(["Vessel", 42], [call]), "42");
});

test("SVG titles contain one text node so browser parsing preserves server markup", async () => {
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { NetworkView } = await import("../app/components/NetworkView");
  const html = renderToStaticMarkup(createElement(NetworkView, {
    network: { focus: 1, nodes: [episode], edges: [], limited: false },
    trace: { kind: "Episode", key: "", from: { kind: "PortCall", key: "1" }, to: { kind: "PortCall", key: "2" } },
  }));
  const title = html.match(/<title>(.*?)<\/title>/)?.[1];
  assert.equal(title, `Berth overlap · ${episode.ref[1]}`);
});
