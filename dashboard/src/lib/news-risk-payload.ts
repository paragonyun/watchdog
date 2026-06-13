import { hasForbiddenCloudField } from "./dashboard-payload";

export type NewsRiskPriority = "urgent" | "caution" | "watch";
export type NewsRiskStatus = "actual" | "delayed" | "refresh_required";
export type NewsRiskFreshness = "new" | "active" | "refresh_required";

export type NewsRiskItem = {
  risk_id: string;
  scope: "direct" | "market";
  priority: NewsRiskPriority;
  title: string;
  category: "금리" | "환율" | "경기" | "규제" | "지정학" | "유동성" | "산업";
  source_type: Array<"rss_rule" | "codex_research">;
  facts: string[];
  potential_impact: string;
  transmission_path: string;
  related_assets: string[];
  related_asset_groups: Array<"isa" | "coin" | "cash">;
  related_asset_weight_pct: number;
  watch_indicators: string[];
  counter_evidence: string[];
  priority_reasons: string[];
  source_links: Array<{ title: string; url: string }>;
  first_seen_at: string;
  last_updated_at: string;
  freshness: NewsRiskFreshness;
  change_reason: string | null;
};

export type NewsRiskPayload = {
  schema_version: "news_risk_payload_v1";
  generated_at: string;
  lookback_hours: 72;
  rss_generated_at: string | null;
  codex_generated_at: string | null;
  status: NewsRiskStatus;
  direct_risks: NewsRiskItem[];
  market_risks: NewsRiskItem[];
};

const priorities = new Set(["urgent", "caution", "watch"]);
const statuses = new Set(["actual", "delayed", "refresh_required"]);
const freshnessValues = new Set(["new", "active", "refresh_required"]);
const categories = new Set(["금리", "환율", "경기", "규제", "지정학", "유동성", "산업"]);
const sourceTypes = new Set(["rss_rule", "codex_research"]);
const assetGroups = new Set(["isa", "coin", "cash"]);

export function validateNewsRiskPayload(value: unknown): value is NewsRiskPayload {
  if (!isRecord(value) || hasForbiddenCloudField(value)) return false;
  return (
    value.schema_version === "news_risk_payload_v1" &&
    isIsoDatetime(value.generated_at) &&
    value.lookback_hours === 72 &&
    isNullableIsoDatetime(value.rss_generated_at) &&
    isNullableIsoDatetime(value.codex_generated_at) &&
    typeof value.status === "string" &&
    statuses.has(value.status) &&
    Array.isArray(value.direct_risks) &&
    value.direct_risks.every((risk) => validateRiskItem(risk, "direct")) &&
    Array.isArray(value.market_risks) &&
    value.market_risks.every((risk) => validateRiskItem(risk, "market"))
  );
}

function validateRiskItem(value: unknown, expectedScope: "direct" | "market"): value is NewsRiskItem {
  if (!isRecord(value) || value.scope !== expectedScope || hasForbiddenCloudField(value)) return false;
  if (
    !nonEmptyString(value.risk_id) ||
    !nonEmptyString(value.title) ||
    !nonEmptyString(value.potential_impact) ||
    !nonEmptyString(value.transmission_path) ||
    typeof value.priority !== "string" ||
    !priorities.has(value.priority) ||
    typeof value.category !== "string" ||
    !categories.has(value.category) ||
    typeof value.freshness !== "string" ||
    !freshnessValues.has(value.freshness) ||
    !Number.isFinite(value.related_asset_weight_pct) ||
    !isIsoDatetime(value.first_seen_at) ||
    !isIsoDatetime(value.last_updated_at) ||
    !(value.change_reason === null || typeof value.change_reason === "string")
  ) {
    return false;
  }
  if (
    !stringList(value.source_type) ||
    !value.source_type.every((item) => sourceTypes.has(item)) ||
    !stringList(value.facts) ||
    !stringList(value.related_assets) ||
    !stringList(value.related_asset_groups) ||
    !value.related_asset_groups.every((item) => assetGroups.has(item)) ||
    !stringList(value.watch_indicators) ||
    !stringList(value.counter_evidence) ||
    !stringList(value.priority_reasons) ||
    !sourceLinks(value.source_links)
  ) {
    return false;
  }
  return expectedScope === "direct" ? value.related_assets.length > 0 : value.related_asset_groups.length > 0;
}

function sourceLinks(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.every(
      (link) =>
        isRecord(link) &&
        nonEmptyString(link.title) &&
        nonEmptyString(link.url) &&
        safeExternalHttpUrl(link.url),
    )
  );
}

function safeExternalHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return false;
    const hostname = url.hostname.toLowerCase().replace(/^\[|\]$/g, "");
    if (!hostname.includes(".") || hostname === "localhost" || hostname.endsWith(".localhost") || hostname.endsWith(".local")) return false;
    if (/^(127\.|10\.|0\.|169\.254\.)/.test(hostname)) return false;
    if (/^192\.168\./.test(hostname)) return false;
    const match = hostname.match(/^172\.(\d{1,3})\./);
    if (match && Number(match[1]) >= 16 && Number(match[1]) <= 31) return false;
    return hostname !== "::1" && !hostname.startsWith("fc") && !hostname.startsWith("fd") && !hostname.startsWith("fe80");
  } catch {
    return false;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function stringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isIsoDatetime(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value) &&
    !Number.isNaN(Date.parse(value))
  );
}

function isNullableIsoDatetime(value: unknown): value is string | null {
  return value === null || isIsoDatetime(value);
}
