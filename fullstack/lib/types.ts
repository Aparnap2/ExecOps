// API Types for FounderOS

export type DecisionState = "CONFIDENT" | "UNCERTAIN" | "ESCALATE";

export interface EventPayload {
  source: "slack" | "gmail" | "stripe" | "hubspot" | "custom";
  occurred_at: string;
  external_id?: string;
  data: Record<string, unknown>;
}

export interface DecisionRequest {
  request_id: string;
  objective: "lead_hygiene" | "support_triage" | "ops_hygiene" | "all";
  events: EventPayload[];
  constraints?: Record<string, unknown>;
}

export interface ConfidenceBreakdown {
  data_completeness: number;
  ambiguity: number;
  rule_violations: number;
}

export interface ActionRecommendation {
  type: string;
  target?: string;
  payload: Record<string, unknown>;
  reason: string;
}

export interface EscalationItem {
  reason: string;
  severity: "high" | "medium" | "low";
  context: Record<string, unknown>;
  suggested_actions: ActionRecommendation[];
}

export interface DecisionResponse {
  request_id: string;
  state: DecisionState;
  summary: string;
  confidence: number;
  confidence_breakdown?: ConfidenceBreakdown;
  recommendations: ActionRecommendation[];
  escalations: EscalationItem[];
  executed_sops: string[];
}

export interface Decision {
  id: string;
  request_id: string;
  objective: string;
  state: DecisionState;
  summary: string;
  confidence: number;
  created_at: string;
}

export interface Event {
  id: string;
  source: string;
  occurred_at: string;
  external_id?: string;
  payload: Record<string, unknown>;
  created_at: string;
}
