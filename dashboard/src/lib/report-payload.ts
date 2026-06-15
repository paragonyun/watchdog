import { hasForbiddenCloudField, type AssetSummary } from "./dashboard-payload";

export type LegacyReportPayload = {
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

export type ResearchReportPayload = Omit<LegacyReportPayload, "schema_version" | "document_status" | "sections"> & {
  schema_version: "dashboard_report_v2";
  document_status: "final";
  subtitle: string;
  stance: "positive" | "neutral" | "cautious";
  executive_summary: string[];
  key_metrics: Array<{ label: string; value: string; context: string; tone: "positive" | "neutral" | "negative" }>;
  investment_thesis: {
    headline: string;
    body: string;
    facts: string[];
    interpretations: string[];
    estimates: string[];
  };
  asset_views: Array<{
    symbol: string;
    name: string;
    action: "buy" | "sell" | "observe";
    thesis: string;
    catalysts: string[];
    risks: string[];
  }>;
  scenarios: Array<{ name: string; probability: string; trigger: string; impact: string; response: string }>;
  risk_watchlist: string[];
  conclusion: string;
};

export type ReportPayload = LegacyReportPayload | ResearchReportPayload;

export type ReportIndexItem = Pick<
  ReportPayload,
  "report_id" | "generated_at" | "report_kind" | "title" | "document_status" | "summary"
> & { schema_version?: ReportPayload["schema_version"] };

const reportIdPattern = /^(portfolio|weekly)-\d{8}-\d{4}$/;

export function validateReportPayload(value: unknown): value is ReportPayload {
  if (!isRecord(value) || hasForbiddenCloudField(value)) return false;
  return (
    (value.schema_version === "dashboard_report_v1" || value.schema_version === "dashboard_report_v2") &&
    validReportId(value.report_id) &&
    (value.schema_version === undefined || value.schema_version === "dashboard_report_v1" || value.schema_version === "dashboard_report_v2") &&
    isIsoDatetime(value.generated_at) &&
    (value.report_kind === "portfolio" || value.report_kind === "weekly") &&
    nonEmptyString(value.title) &&
    (value.document_status === "source" || value.document_status === "final") &&
    validSummary(value.summary) &&
    validAppendix(value.appendix) &&
    (value.schema_version === "dashboard_report_v1" ? validLegacyBody(value) : validResearchBody(value))
  );
}

export function isResearchReport(payload: ReportPayload): payload is ResearchReportPayload {
  return payload.schema_version === "dashboard_report_v2";
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
    schema_version: payload.schema_version,
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

function validLegacyBody(value: Record<string, unknown>): boolean {
  return Array.isArray(value.sections) && value.sections.length > 0 && value.sections.every(validSection);
}

function validResearchBody(value: Record<string, unknown>): boolean {
  return (
    value.document_status === "final" &&
    nonEmptyString(value.subtitle) &&
    (value.stance === "positive" || value.stance === "neutral" || value.stance === "cautious") &&
    nonEmptyStringList(value.executive_summary) &&
    Array.isArray(value.key_metrics) &&
    value.key_metrics.length > 0 &&
    value.key_metrics.every(validKeyMetric) &&
    validThesis(value.investment_thesis) &&
    Array.isArray(value.asset_views) &&
    value.asset_views.length > 0 &&
    value.asset_views.every(validAssetView) &&
    Array.isArray(value.scenarios) &&
    value.scenarios.length > 0 &&
    value.scenarios.every(validScenario) &&
    nonEmptyStringList(value.risk_watchlist) &&
    nonEmptyString(value.conclusion)
  );
}

function validKeyMetric(value: unknown): boolean {
  return isRecord(value) && nonEmptyString(value.label) && nonEmptyString(value.value) && nonEmptyString(value.context) &&
    (value.tone === "positive" || value.tone === "neutral" || value.tone === "negative");
}

function validThesis(value: unknown): boolean {
  return isRecord(value) && nonEmptyString(value.headline) && nonEmptyString(value.body) &&
    nonEmptyStringList(value.facts) && nonEmptyStringList(value.interpretations) && nonEmptyStringList(value.estimates);
}

function validAssetView(value: unknown): boolean {
  return isRecord(value) && nonEmptyString(value.symbol) && nonEmptyString(value.name) && nonEmptyString(value.thesis) &&
    (value.action === "buy" || value.action === "sell" || value.action === "observe") &&
    nonEmptyStringList(value.catalysts) && nonEmptyStringList(value.risks);
}

function validScenario(value: unknown): boolean {
  return isRecord(value) && ["name", "probability", "trigger", "impact", "response"].every((key) => nonEmptyString(value[key]));
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

function nonEmptyStringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.length > 0 && value.every(nonEmptyString);
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
