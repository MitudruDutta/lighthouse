import type { GraphNode, Ref } from "./api";

export const ENTITY_KINDS = ["Port", "PortCall", "Vessel", "Berth"];

/** Keep the exact record identifier in details; give the visible heading a human label. */
export function nodeTitle(node: GraphNode): string {
  if (node.ref[0] === "Episode" && node.title === String(node.ref[1])) {
    if (node.title.startsWith("berth-overload:")) return "Berth overlap";
    if (node.title.startsWith("port-activity:")) return "Unusual port activity";
    return "Investigation episode";
  }
  if (node.ref[0] === "PortCall" && node.title === String(node.ref[1])) return `Port call ${node.title}`;
  if (node.ref[0] === "Entry") return node.title.charAt(0).toUpperCase() + node.title.slice(1);
  return node.title;
}

export function refTitle(ref: Ref, nodes: GraphNode[]): string {
  const found = nodes.find((node) => node.ref[0] === ref[0] && String(node.ref[1]) === String(ref[1]));
  return found ? nodeTitle(found) : String(ref[1]);
}
