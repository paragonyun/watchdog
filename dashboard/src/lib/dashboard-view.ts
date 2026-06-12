import type {
  AssetSummary,
  DashboardPayload,
  DashboardPayloadV2,
  DashboardV2Asset,
} from "./dashboard-payload";

export type DashboardView = {
  generatedAt: string | null;
  totalValueKrw: number;
  status: string;
  lastActualAt: string | null;
  periodChange: { changeKrw: number | null; changePct: number | null };
  performance: {
    cumulativeTwrPct: number | null;
    monthTwrPct: number | null;
    benchmarkReturnPct: number | null;
    excessReturnPct: number | null;
    maxDrawdownPct: number | null;
    status: string;
  };
  groups: Array<{
    key: "isa" | "coin" | "cash";
    label: string;
    valueKrw: number;
    weightPercent: number;
    targetWeightPercent: number | null;
    targetDiffPercentagePoints: number | null;
  }>;
  assets: Array<{
    symbol: string;
    name: string;
    assetType: string;
    valueKrw: number;
    weightPercent: number;
    profitLossRatePercent: number | null;
    targetDiffPercentagePoints: number | null;
    priceSource: string | null;
  }>;
  news: DashboardPayload["news_impacts"];
  attention: Array<{ level: "high" | "medium"; title: string; detail: string }>;
  opinions: [];
  calendar: [];
  reports: [];
  providers: Array<{ provider: string; status: string; usedFallback: boolean }>;
};

const GROUPS = [
  { key: "isa" as const, legacyKey: "equity" as const, label: "ISA" },
  { key: "coin" as const, legacyKey: "coin" as const, label: "코인" },
  { key: "cash" as const, legacyKey: "cash" as const, label: "현금 및 예수금" },
];

export function buildDashboardView(v1: DashboardPayload | null, v2: DashboardPayloadV2 | null): DashboardView {
  const totalValueKrw = v2?.total_value_krw ?? v1?.total_value_krw ?? 0;
  const attention: DashboardView["attention"] = [];
  const freshness = v2?.data_freshness;
  const performance = v2?.performance;

  if (freshness?.portfolio_status && freshness.portfolio_status !== "actual") {
    attention.push({ level: "high", title: "데이터 최신성 확인 필요", detail: `현재 상태: ${freshness.portfolio_status}` });
  }
  if (freshness?.reconciliation_status === "reconciliation_required") {
    attention.push({ level: "high", title: "보유수량 대사 필요", detail: "거래내역과 현재 보유수량의 차이를 확인해야 합니다." });
  }
  if (performance?.status === "provisional") {
    attention.push({ level: "medium", title: "성과 수치 잠정 상태", detail: "현금흐름 또는 대사 확인 후 확정됩니다." });
  }

  return {
    generatedAt: v2?.generated_at ?? v1?.generated_at ?? null,
    totalValueKrw,
    status: freshness?.portfolio_status ?? (v1 ? "actual" : "unavailable"),
    lastActualAt: freshness?.last_actual_at ?? v1?.generated_at ?? null,
    periodChange: {
      changeKrw: v1?.trend.change_krw ?? null,
      changePct: v1?.trend.change_pct ?? null,
    },
    performance: {
      cumulativeTwrPct: performance?.cumulative_twr_pct ?? null,
      monthTwrPct: performance?.month_twr_pct ?? null,
      benchmarkReturnPct: performance?.benchmark_return_pct ?? null,
      excessReturnPct: performance?.excess_return_pct ?? null,
      maxDrawdownPct: performance?.max_drawdown_pct ?? null,
      status: performance?.status ?? "insufficient_data",
    },
    groups: GROUPS.map((meta) => buildGroup(meta, v1, v2, totalValueKrw)),
    assets: mergeAssets(v1?.assets ?? [], v2?.assets ?? []),
    news: v1?.news_impacts ?? [],
    attention,
    opinions: [],
    calendar: [],
    reports: [],
    providers: buildProviders(v1, v2),
  };
}

function buildGroup(
  meta: (typeof GROUPS)[number],
  v1: DashboardPayload | null,
  v2: DashboardPayloadV2 | null,
  totalValueKrw: number,
): DashboardView["groups"][number] {
  const group = v2?.asset_groups.find((item) => item.asset_group === meta.key);
  const valueKrw = group?.value_krw ?? v1?.asset_groups[meta.legacyKey] ?? 0;
  const weightPercent = group?.weight_percent ?? (totalValueKrw > 0 ? (valueKrw / totalValueKrw) * 100 : 0);
  const diff = group?.target_diff_percentage_points ?? null;
  return {
    key: meta.key,
    label: meta.label,
    valueKrw,
    weightPercent,
    targetWeightPercent: diff === null ? null : weightPercent - diff,
    targetDiffPercentagePoints: diff,
  };
}

function mergeAssets(v1Assets: AssetSummary[], v2Assets: DashboardV2Asset[]): DashboardView["assets"] {
  const v1BySymbol = new Map(v1Assets.map((asset) => [asset.symbol, asset]));
  const v2BySymbol = new Map(v2Assets.map((asset) => [asset.symbol, asset]));
  const symbols = new Set([...v1BySymbol.keys(), ...v2BySymbol.keys()]);
  return [...symbols]
    .map((symbol) => {
      const legacy = v1BySymbol.get(symbol);
      const current = v2BySymbol.get(symbol);
      return {
        symbol,
        name: current?.name ?? legacy?.name ?? symbol,
        assetType: normalizeAssetType(current?.asset_type ?? legacy?.asset_type ?? ""),
        valueKrw: current?.value_krw ?? legacy?.value_krw ?? 0,
        weightPercent: current?.weight_percent ?? legacy?.weight_percent ?? 0,
        profitLossRatePercent:
          current?.cumulative_profit_loss_rate_percent ??
          current?.profit_loss_rate_percent ??
          legacy?.profit_loss_rate_percent ??
          null,
        targetDiffPercentagePoints: current?.target_diff_percentage_points ?? null,
        priceSource: legacy?.price_source ?? null,
      };
    })
    .sort((a, b) => b.valueKrw - a.valueKrw);
}

function buildProviders(v1: DashboardPayload | null, v2: DashboardPayloadV2 | null): DashboardView["providers"] {
  if (v2?.provider_status.length) {
    return v2.provider_status.map((item) => ({
      provider: item.provider,
      status: item.status ?? (item.used_fallback ? "fallback" : "actual"),
      usedFallback: item.used_fallback ?? false,
    }));
  }
  return (v1?.provider_status ?? []).map((item) => ({
    provider: item.provider,
    status: item.used_fallback ? "fallback" : "actual",
    usedFallback: item.used_fallback,
  }));
}

function normalizeAssetType(value: string): string {
  return value === "equity" ? "isa" : value;
}
