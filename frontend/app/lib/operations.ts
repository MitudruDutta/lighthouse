import {
  segments,
  type Checked,
  type Entry,
  type Episode,
  type Ref,
} from "./api";

export type Profile = {
  name: string;
  timezone: string;
  focus: "all" | "finland" | "global";
  view?: "attention" | "watching" | "mine";
  ports: string[];
  vessels: string[];
};
export type CaseStatus =
  | "queued"
  | "investigating"
  | "needs_review"
  | "resolved"
  | "source_cleared";
export type Case = {
  id: string;
  title: string;
  impact: string;
  scope: "finland" | "global";
  port: string;
  observation_at: string;
  opened_at: string;
  source_cleared: boolean;
  status: CaseStatus;
  owner: string | null;
  revision: number;
  action: string;
  action_status: string;
  outcome: string;
  updated_at: string | null;
  assessment: (Entry & Checked) | null;
  about: Ref[];
  watching: boolean;
  mine: boolean;
};
export type Queue = {
  cases: Case[];
  profile: Profile;
  user: string;
  limited: boolean;
};
export type CaseDetail = {
  case: Case;
  source: Episode;
  profile: Profile;
  user: string;
  prior_outcomes: {
    id: string;
    action: string;
    outcome: string;
    updated_at: string;
    updated_by: string;
  }[];
  events: {
    revision: number;
    operation: string;
    text: string;
    by: string;
    at: string;
  }[];
};
export const STATUS: Record<CaseStatus, string> = {
  queued: "Queued",
  investigating: "Investigating",
  needs_review: "Needs review",
  resolved: "Resolved",
  source_cleared: "Source cleared",
};
export const caseHref = (id: string) => `/cases/${segments(id)}`;
export function active(item: Case) {
  return item.status !== "resolved" && item.status !== "source_cleared";
}
