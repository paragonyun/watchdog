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

export type ReportQualityStatus = "pass" | "review";

export type ReportQualityCheck = {
  id: "document" | "executive" | "evidence" | "asset_views" | "scenarios" | "appendix" | "providers";
  label: string;
  status: ReportQualityStatus;
  detail: string;
};

export type ReportQualityView = {
  status: ReportQualityStatus;
  summary: string;
  checks: ReportQualityCheck[];
};

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

export function buildReportQualityView(payload: ReportPayload): ReportQualityView {
  const providerFallbacks = payload.appendix.provider_status.filter((provider) => provider.used_fallback);
  const checks: ReportQualityCheck[] = [
    qualityCheck(
      "document",
      "문서 형태",
      isResearchReport(payload),
      isResearchReport(payload)
        ? "완성 리서치 리포트 형식입니다."
        : "작성 원본입니다. Codex 최종 리포트 동기화가 필요합니다.",
    ),
    qualityCheck(
      "appendix",
      "숫자 검증",
      payload.summary.validation_valid && payload.appendix.validation_issues.length === 0,
      payload.appendix.validation_issues.length
        ? payload.appendix.validation_issues.join(" / ")
        : "총액, 비중, 변동률 기본 검증을 통과했습니다.",
    ),
    qualityCheck(
      "providers",
      "데이터 출처",
      providerFallbacks.length === 0,
      providerFallbacks.length
        ? `${providerFallbacks.map((provider) => provider.provider).join(", ")} fallback 사용`
        : "주요 데이터 출처가 live 상태입니다.",
    ),
  ];

  if (isResearchReport(payload)) {
    checks.splice(
      1,
      0,
      qualityCheck(
        "executive",
        "핵심 요약",
        payload.executive_summary.length >= 3 && payload.key_metrics.length >= 3,
        payload.executive_summary.length >= 3 && payload.key_metrics.length >= 3
          ? "최종 판단, 핵심 숫자, 다음 행동을 앞부분에서 요약합니다."
          : "핵심 요약과 주요 지표는 각각 3개 이상으로 보강하는 편이 좋습니다.",
      ),
      qualityCheck(
        "evidence",
        "사실/해석/추정",
        payload.investment_thesis.facts.length > 0 &&
          payload.investment_thesis.interpretations.length > 0 &&
          payload.investment_thesis.estimates.length > 0,
        "투자 논리의 근거 레이어를 분리해 표시합니다.",
      ),
      qualityCheck(
        "asset_views",
        "자산별 판단",
        payload.asset_views.length > 0 &&
          payload.asset_views.every((view) => view.catalysts.length > 0 && view.risks.length > 0),
        "각 자산에 매수, 매도, 관찰 판단과 촉매/위험을 포함합니다.",
      ),
      qualityCheck(
        "scenarios",
        "시나리오",
        payload.scenarios.length >= 3,
        payload.scenarios.length >= 3
          ? "상승, 기준, 하락 시나리오를 모두 포함합니다."
          : "상승, 기준, 하락 시나리오 3개 이상으로 보강하는 편이 좋습니다.",
      ),
    );
  }

  const status = checks.every((check) => check.status === "pass") ? "pass" : "review";
  return {
    status,
    summary:
      status === "pass"
        ? "리포트 본문, 근거, 시나리오, 부록 QC를 통과했습니다."
        : "일부 리포트 품질 항목은 보강하거나 재검토하는 편이 좋습니다.",
    checks,
  };
}

function qualityCheck(
  id: ReportQualityCheck["id"],
  label: string,
  passed: boolean,
  detail: string,
): ReportQualityCheck {
  return { id, label, status: passed ? "pass" : "review", detail };
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
