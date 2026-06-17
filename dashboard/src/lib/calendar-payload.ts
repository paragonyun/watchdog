import { hasForbiddenCloudField } from "./dashboard-payload";

export type CalendarImportance = "low" | "medium" | "high";
export type CalendarAssetGroup = "isa" | "coin" | "cash";

export type CalendarEvent = {
  id: string;
  title: string;
  starts_at: string;
  country: string;
  category: string;
  importance: CalendarImportance;
  asset_groups: CalendarAssetGroup[];
  expected_impact: string;
  watch_note: string;
  source_url: string | null;
};

export type CalendarPayload = {
  schema_version: "dashboard_calendar_v1";
  generated_at: string;
  source: string;
  timezone: "Asia/Seoul";
  events: CalendarEvent[];
};

const importances = new Set(["low", "medium", "high"]);
const assetGroups = new Set(["isa", "coin", "cash"]);

export function validateCalendarPayload(value: unknown): value is CalendarPayload {
  if (!isRecord(value) || hasForbiddenCloudField(value)) return false;
  return (
    value.schema_version === "dashboard_calendar_v1" &&
    isIsoDatetime(value.generated_at) &&
    nonEmptyString(value.source) &&
    value.timezone === "Asia/Seoul" &&
    Array.isArray(value.events) &&
    value.events.every(validEvent)
  );
}

function validEvent(value: unknown): value is CalendarEvent {
  if (!isRecord(value) || hasForbiddenCloudField(value)) return false;
  return (
    ["id", "title", "country", "category", "expected_impact", "watch_note"].every((key) => nonEmptyString(value[key])) &&
    isIsoDatetime(value.starts_at) &&
    typeof value.importance === "string" &&
    importances.has(value.importance) &&
    Array.isArray(value.asset_groups) &&
    value.asset_groups.length > 0 &&
    value.asset_groups.every((group) => typeof group === "string" && assetGroups.has(group)) &&
    (value.source_url === null || (typeof value.source_url === "string" && safeExternalHttpUrl(value.source_url)))
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

function isIsoDatetime(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}
