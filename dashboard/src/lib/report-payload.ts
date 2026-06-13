import { hasForbiddenCloudField, type AssetSummary } from "./dashboard-payload";

export type ReportPayload = {
  schema_version: "dashboard_report_v1";
  report_id: string;
  generated_at: string;
  report_kind: "portfolio" | "weekly";
  title: string;
  document_status: "source" | "final";
  summary: {
    total_value_krw: number;
    change_krw: number;
    change_pct: number | null;
    validation_valid: boolean;
  };
  sections: Array<{ title: string; lines: string[] }>;
  appendix: {
    asset_groups: { coin: number; equity: number; cash: number };
    assets: AssetSummary[];
    provider_status: Array<{ provider: string; used_fallback: boolean }>;
    validation_issues: string[];
  };
};

export type ReportIndexItem = Pick<
  ReportPayload,
  "report_id" | "generated_at" | "report_kind" | "title" | "document_status" | "summary"
>;

const reportIdPattern = /^(portfolio|weekly)-\d{8}-\d{4}$/;

export function validateReportPayload(value: unknown): value is ReportPayload {
  if (!isRecord(value) || hasForbiddenCloudField(value)) return false;
  return (
    value.schema_version === "dashboard_report_v1" &&
    validReportId(value.report_id) &&
    isIsoDatetime(value.generated_at) &&
    (value.report_kind === "portfolio" || value.report_kind === "weekly") &&
    nonEmptyString(value.title) &&
    (value.document_status === "source" || value.document_status === "final") &&
    validSummary(value.summary) &&
    Array.isArray(value.sections) &&
    value.sections.length > 0 &&
    value.sections.every(validSection) &&
    validAppendix(value.appendix)
  );
}

export function validateReportIndexItem(value: unknown): value is ReportIndexItem {
  if (!isRecord(value) || hasForbiddenCloudField(value)) return false;
  return (
    validReportId(value.report_id) &&
    isIsoDatetime(value.generated_at) &&
    (value.report_kind === "portfolio" || value.report_kind === "weekly") &&
    nonEmptyString(value.title) &&
    (value.document_status === "source" || value.document_status === "final") &&
    validSummary(value.summary)
  );
}

export function validReportId(value: unknown): value is string {
  return typeof value === "string" && reportIdPattern.test(value);
}

export function toReportIndexItem(payload: ReportPayload): ReportIndexItem {
  return {
    report_id: payload.report_id,
    generated_at: payload.generated_at,
    report_kind: payload.report_kind,
    title: payload.title,
    document_status: payload.document_status,
    summary: payload.summary,
  };
}

function validSummary(value: unknown): value is ReportPayload["summary"] {
  return (
    isRecord(value) &&
    finiteNumber(value.total_value_krw) &&
    finiteNumber(value.change_krw) &&
    nullableFiniteNumber(value.change_pct) &&
    typeof value.validation_valid === "boolean"
  );
}

function validSection(value: unknown): boolean {
  return (
    isRecord(value) &&
    nonEmptyString(value.title) &&
    stringList(value.lines) &&
    value.lines.every((line) => line.trim().length > 0)
  );
}

function validAppendix(value: unknown): boolean {
  if (!isRecord(value) || !isRecord(value.asset_groups)) return false;
  return (
    finiteNumber(value.asset_groups.coin) &&
    finiteNumber(value.asset_groups.equity) &&
    finiteNumber(value.asset_groups.cash) &&
    Array.isArray(value.assets) &&
    value.assets.every(validAsset) &&
    Array.isArray(value.provider_status) &&
    value.provider_status.every(validProvider) &&
    stringList(value.validation_issues)
  );
}

function validAsset(value: unknown): boolean {
  return (
    isRecord(value) &&
    nonEmptyString(value.symbol) &&
    nonEmptyString(value.name) &&
    nonEmptyString(value.asset_type) &&
    finiteNumber(value.value_krw) &&
    finiteNumber(value.weight_percent) &&
    nullableFiniteNumber(value.profit_loss_rate_percent) &&
    nonEmptyString(value.price_source)
  );
}

function validProvider(value: unknown): boolean {
  return (
    isRecord(value) &&
    nonEmptyString(value.provider) &&
    typeof value.used_fallback === "boolean"
  );
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

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function nullableFiniteNumber(value: unknown): value is number | null {
  return value === null || finiteNumber(value);
}

function isIsoDatetime(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}
