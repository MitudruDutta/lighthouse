// Plans on the landing page and in the console. Billing is not active in the preview: every
// hosted account is on Developer, with the limits the Memory API enforces today.
export const LIMITS = {
  workspaces: 5,
  projectsPerWorkspace: 20,
  keysPerProject: 20,
  requestsPerMinute: 120,
};

export type Plan = {
  id: string;
  name: string;
  price: string;
  cadence: string;
  summary: string;
  features: string[];
  action: string;
  href: "docs" | "signup" | null;
  current?: boolean;
  soon?: boolean;
};

export const PLANS: Plan[] = [
  {
    id: "open-source",
    name: "Open source",
    price: "$0",
    cadence: "forever",
    summary: "The library on your own FalkorDB.",
    features: [
      "pip install lighthouse-graph, Apache-2.0",
      "Versions, episodes, lessons, tasks, conversations",
      "Graph, text, and vector recall",
      "No model calls when it writes",
    ],
    action: "Read the quickstart",
    href: "docs",
  },
  {
    id: "developer",
    name: "Developer",
    price: "$0",
    cadence: "during the preview",
    summary: "Hosted memory for your agents, with an MCP endpoint.",
    features: [
      `${LIMITS.workspaces} workspaces, ${LIMITS.projectsPerWorkspace} projects each`,
      `${LIMITS.keysPerProject} active API keys per project`,
      `${LIMITS.requestsPerMinute} requests a minute per key`,
      "MCP server and Claude Code plugin",
      "Console, memory explorer, usage",
    ],
    action: "Start building",
    href: "signup",
    current: true,
  },
  {
    id: "pro",
    name: "Pro",
    price: "$29",
    cadence: "per workspace a month",
    summary: "For agents that run in production.",
    features: [
      "Ten times the request limit",
      "100 projects per workspace",
      "Daily graph backups",
      "A year of usage history",
      "Email support",
    ],
    action: "Coming soon",
    href: null,
    soon: true,
  },
  {
    id: "enterprise",
    name: "Enterprise",
    price: "Custom",
    cadence: "annual agreement",
    summary: "Dedicated FalkorDB, in your cloud or ours.",
    features: [
      "Dedicated or self-hosted graph",
      "Single sign-on and team roles",
      "Uptime agreement",
      "Security review support",
    ],
    action: "Coming soon",
    href: null,
    soon: true,
  },
];
