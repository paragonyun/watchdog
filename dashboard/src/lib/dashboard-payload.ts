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

export function validateDashboardPayload(value: unknown): value is DashboardPayload {
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
