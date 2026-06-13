export type AssetSummary = {
  symbol: string;
  name: string;
  asset_type: "coin" | "equity" | "cash" | string;
  value_krw: number;
  weight_percent: number;
  profit_loss_rate_percent: number | null;
  price_source: string;
};

export type DashboardPayload = {
  schema_version: "dashboard_payload_v1";
  generated_at: string | null;
  report_kind: string | null;
  total_value_krw: number;
  asset_groups: {
    coin: number;
    equity: number;
    cash: number;
  };
  assets: AssetSummary[];
  trend: {
    start_at?: string | null;
    latest_at?: string | null;
    start_total_krw: number;
    latest_total_krw: number;
    change_krw: number;
    change_pct: number | null;
    snapshot_count: number;
  };
  news_impacts: Array<{
    title: string;
    impact: string;
    impact_score: number;
    score_label: string;
    related_assets: string[];
    reason: string;
    why_it_matters: string;
    url?: string | null;
  }>;
  provider_status: Array<{
    provider: string;
    used_fallback: boolean;
  }>;
};

export type DashboardV2AssetGroup = {
  asset_group: "isa" | "coin" | "cash" | string;
  value_krw?: number;
  weight_percent?: number;
  target_diff_percentage_points?: number;
  profit_loss_rate_percent?: number | null;
  cumulative_profit_loss_rate_percent?: number | null;
};

export type DashboardV2Asset = {
  symbol: string;
  name?: string;
  asset_type: "isa" | "coin" | "cash" | string;
  value_krw?: number;
  weight_percent?: number;
  target_diff_percentage_points?: number;
  profit_loss_rate_percent?: number | null;
  cumulative_profit_loss_rate_percent?: number | null;
};

export type DashboardPayloadV2 = {
  schema_version: "dashboard_payload_v2";
  generated_at: string | null;
  total_value_krw: number;
  data_freshness: {
    portfolio_status?: "actual" | "estimated" | "stale" | "fallback";
    last_actual_at?: string | null;
    reconciliation_status?: "reconciled" | "reconciliation_required";
  };
  performance: {
    cumulative_twr_pct?: number | null;
    month_twr_pct?: number | null;
    benchmark_return_pct?: number | null;
    excess_return_pct?: number | null;
    max_drawdown_pct?: number | null;
    status?: "confirmed" | "provisional" | "insufficient_data";
  };
  asset_groups: DashboardV2AssetGroup[];
  assets: DashboardV2Asset[];
  provider_status: Array<{
    provider: string;
    status?: string;
    used_fallback?: boolean;
    last_actual_at?: string | null;
  }>;
};

export type AnyDashboardPayload = DashboardPayload | DashboardPayloadV2;

export function validateDashboardPayloadV1(value: unknown): value is DashboardPayload {
  if (!value || typeof value !== "object") {
    return false;
  }
  const payload = value as Partial<DashboardPayload>;
  return (
    payload.schema_version === "dashboard_payload_v1" &&
    typeof payload.total_value_krw === "number" &&
    !!payload.asset_groups &&
    typeof payload.asset_groups.coin === "number" &&
    typeof payload.asset_groups.equity === "number" &&
    typeof payload.asset_groups.cash === "number" &&
    Array.isArray(payload.assets) &&
    Array.isArray(payload.news_impacts) &&
    Array.isArray(payload.provider_status)
  );
}

export function validateDashboardPayloadV2(value: unknown): value is DashboardPayloadV2 {
  if (!value || typeof value !== "object") {
    return false;
  }
  const payload = value as Partial<DashboardPayloadV2>;
  return (
    payload.schema_version === "dashboard_payload_v2" &&
    typeof payload.total_value_krw === "number" &&
    isRecord(payload.data_freshness) &&
    isRecord(payload.performance) &&
    optionalFiniteNumber(payload.performance.cumulative_twr_pct) &&
    optionalFiniteNumber(payload.performance.month_twr_pct) &&
    optionalFiniteNumber(payload.performance.benchmark_return_pct) &&
    optionalFiniteNumber(payload.performance.excess_return_pct) &&
    optionalFiniteNumber(payload.performance.max_drawdown_pct) &&
    Array.isArray(payload.asset_groups) &&
    payload.asset_groups.every(validateV2AssetGroup) &&
    Array.isArray(payload.assets) &&
    payload.assets.every(validateV2Asset) &&
    Array.isArray(payload.provider_status) &&
    payload.provider_status.every(validateV2Provider) &&
    !hasForbiddenCloudField(value)
  );
}

export function validateDashboardPayload(value: unknown): value is AnyDashboardPayload {
  return validateDashboardPayloadV1(value) || validateDashboardPayloadV2(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function optionalFiniteNumber(value: unknown): boolean {
  return value === undefined || value === null || (typeof value === "number" && Number.isFinite(value));
}

function validateV2AssetGroup(value: unknown): boolean {
  if (!isRecord(value) || typeof value.asset_group !== "string") {
    return false;
  }
  return [
    value.value_krw,
    value.weight_percent,
    value.target_diff_percentage_points,
    value.profit_loss_rate_percent,
    value.cumulative_profit_loss_rate_percent,
  ].every(optionalFiniteNumber);
}

function validateV2Asset(value: unknown): boolean {
  if (!isRecord(value) || typeof value.symbol !== "string" || typeof value.asset_type !== "string") {
    return false;
  }
  return [
    value.value_krw,
    value.weight_percent,
    value.target_diff_percentage_points,
    value.profit_loss_rate_percent,
    value.cumulative_profit_loss_rate_percent,
  ].every(optionalFiniteNumber);
}

function validateV2Provider(value: unknown): boolean {
  return isRecord(value) && typeof value.provider === "string" && (value.used_fallback === undefined || typeof value.used_fallback === "boolean");
}

const FORBIDDEN_CLOUD_FIELDS = new Set([
  "quantity",
  "current_quantity",
  "average_buy_price_krw",
  "account_no",
  "account_product_code",
  "order_id",
  "order_no",
  "uuid",
  "access_key",
  "api_key",
  "app_key",
  "secret_key",
  "app_secret",
  "raw_response",
  "raw_api_response",
  "memo",
]);

export function hasForbiddenCloudField(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.some(hasForbiddenCloudField);
  }
  if (!isRecord(value)) {
    return false;
  }
  return Object.entries(value).some(([key, child]) => FORBIDDEN_CLOUD_FIELDS.has(key.toLowerCase()) || hasForbiddenCloudField(child));
}
