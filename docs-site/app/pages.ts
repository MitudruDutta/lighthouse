// Memory library documentation, in reading order.
export const PARTS: [string, [string, string][]][] = [
  [
    "Start",
    [
      ["/", "Overview"],
      ["/library", "Quickstart"],
      ["/showcase", "Use cases"],
      ["/integrations", "Models & agent integration"],
    ],
  ],
  [
    "Memory",
    [
      ["/model", "Memory model"],
      ["/history", "Versioned entities & history"],
      ["/episodes", "Episodes & evidence"],
      ["/learning", "Lessons & playbooks"],
      ["/coordination", "Tasks & handoffs"],
      ["/conversations", "Conversation memory"],
    ],
  ],
  [
    "Retrieval",
    [
      ["/recall", "Graph, text & vector recall"],
      ["/algorithms", "Graph algorithms"],
      ["/mcp", "Expose memory through MCP"],
    ],
  ],
  [
    "FalkorDB",
    [
      ["/tenants", "Graphs & tenant isolation"],
      ["/falkordb", "Capabilities & behaviour"],
      ["/security", "Security & limits"],
    ],
  ],
  [
    "Reference",
    [
      ["/reference", "Python API"],
      ["/memory-api", "Memory HTTP API"],
    ],
  ],
];
