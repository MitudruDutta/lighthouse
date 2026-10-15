export type Project = {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  created: number;
};
export type Overview = {
  user: { id: string; name: string; email: string; timezone: string };
  workspaces: { id: string; name: string }[];
  projects: Project[];
  plan: { name: string; billing_active: boolean };
};
export type KeyRecord = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created: number;
  expires: number;
  revoked: number | null;
  last_used: number | null;
};
export type Fact = {
  key: string;
  title: string;
  text: string;
  metadata: Record<string, unknown>;
};
export type Summary = {
  counts: Record<string, number>;
  edges: { from: string; to: string }[];
  usage: { operation: string; count: number }[];
  days: { day: string; count: number }[];
  recent: { operation: string; status: number; at: number }[];
};
