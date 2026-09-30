// Mirrors docs/api_contract.md and src/citizengraph/api/schemas.py. Keep in sync.

export type Lang = "en" | "fil";
export type InfoStatus = "confirmed" | "pending_lgu";
export type Group = "business" | "family" | "health" | "assistance";
export type ResponseKind = "answer" | "clarify" | "refusal" | "status" | "fallback";

export const GROUPS: Group[] = ["business", "family", "health", "assistance"];

export interface Summary {
  requirement_count: number | null;
  fee_text: string | null;
  time_text: string | null;
}

export interface FeeItem {
  label: string;
  amount_text: string;
}

export interface StepItem {
  order: number;
  text: string;
  time_text: string | null;
  external: boolean;
}

export interface Related {
  label: string;
  office: string;
  note: string;
}

export interface Section {
  service_id: string;
  service_name: string;
  office: string;
  info_status: InfoStatus;
  summary: Summary;
  checklist: string[];
  fees: FeeItem[];
  steps: StepItem[];
  notes: string[];
  related: Related[];
}

export interface ServiceListItem {
  id: string;
  name: string;
  office: string;
  group: Group;
  summary: Summary;
  info_status: InfoStatus;
}

export interface Health {
  status: string;
  mock: boolean;
}

export interface ChatRequest {
  message: string;
  lang: Lang;
  session_id?: string | null;
}

export interface ChatResponse {
  session_id: string;
  language: Lang;
  kind: ResponseKind;
  text: string;
  sections: Section[];
  clarify_options: string[];
  meta: { mock?: boolean; source?: string } & Record<string, unknown>;
}
