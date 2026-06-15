import { hasForbiddenCloudField } from "./dashboard-payload";

export type OpinionAction = "buy" | "sell" | "observe";
export type OpinionConfidence = "low" | "medium" | "high";

export type OpinionPayload = {
  schema_version: "dashboard_opinion_v1";
  opinion_id: string;
  generated_at: string;
  portfolio_posture: OpinionAction;
  summary: string;
  items: Array<{
    id: string;
    symbol: string;
    name: string;
    action: OpinionAction;
    confidence: OpinionConfidence;
    thesis: string;
    evidence: string[];
    counter_evidence: string[];
    catalysts: string[];
    invalidation_conditions: string[];
    suggested_position_note: string;
    sources: Array<{ label: string; url: string | null }>;
  }>;
  disclaimer: string;
};

export function validateOpinionPayload(value: unknown): value is OpinionPayload {
  if (!isRecord(value) || hasForbiddenCloudField(value)) return false;
  return (
    value.schema_version === "dashboard_opinion_v1" &&
    nonEmptyString(value.opinion_id) &&
    isIsoDatetime(value.generated_at) &&
    validAction(value.portfolio_posture) &&
    nonEmptyString(value.summary) &&
    nonEmptyString(value.disclaimer) &&
    Array.isArray(value.items) &&
    value.items.length > 0 &&
    value.items.every(validItem)
  );
}

function validItem(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return (
    ["id", "symbol", "name", "thesis", "suggested_position_note"].every((key) => nonEmptyString(value[key])) &&
    validAction(value.action) &&
    (value.confidence === "low" || value.confidence === "medium" || value.confidence === "high") &&
    ["evidence", "counter_evidence", "catalysts", "invalidation_conditions"].every((key) => stringList(value[key])) &&
    Array.isArray(value.sources) &&
    value.sources.length > 0 &&
    value.sources.every(validSource)
  );
}

function validSource(value: unknown): boolean {
  return isRecord(value) && nonEmptyString(value.label) && (value.url === null || typeof value.url === "string");
}

function validAction(value: unknown): value is OpinionAction {
  return value === "buy" || value === "sell" || value === "observe";
}

function stringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(nonEmptyString);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function isIsoDatetime(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}
