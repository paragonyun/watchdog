import type { DashboardView } from "./dashboard-view";

export type RiskLevel = "high" | "medium" | "low";

export type RiskCheck = {
  id: "single" | "top-three" | "allocation" | "loss" | "data" | "history";
  level: RiskLevel;
  title: string;
  metric: string;
  detail: string;
  threshold: string;
};

export type RiskView = {
  highestLevel: RiskLevel;
  highCount: number;
  mediumCount: number;
  checks: RiskCheck[];
  largestAsset: DashboardView["assets"][number] | null;
  topThreeWeightPercent: number;
  lossExposureWeightPercent: number;
  maxGroupDeviationPercentagePoints: number | null;
  maxDrawdownPct: number | null;
  concentrationAssets: DashboardView["assets"];
  lossAssets: DashboardView["assets"];
  groupDeviations: DashboardView["groups"];
};

const levelRank: Record<RiskLevel, number> = { high: 2, medium: 1, low: 0 };

export function buildRiskView(view: DashboardView): RiskView {
  const concentrationAssets = [...view.assets].sort((left, right) => right.weightPercent - left.weightPercent);
  const largestAsset = concentrationAssets[0] ?? null;
  const topThreeWeightPercent = sum(concentrationAssets.slice(0, 3).map((asset) => asset.weightPercent));
  const lossAssets = view.assets
    .filter((asset) => asset.profitLossRatePercent !== null && asset.profitLossRatePercent <= -20)
    .sort((left, right) => (left.profitLossRatePercent ?? 0) - (right.profitLossRatePercent ?? 0));
  const lossExposureWeightPercent = sum(lossAssets.map((asset) => asset.weightPercent));
  const deviations = view.groups
    .map((group) => Math.abs(group.targetDiffPercentagePoints ?? 0))
    .filter(Number.isFinite);
  const maxGroupDeviationPercentagePoints = deviations.length ? Math.max(...deviations) : null;
  const providersHealthy = view.status === "actual" && view.providers.every((provider) => !provider.usedFallback && provider.status === "actual");

  const checks: RiskCheck[] = [
    {
      id: "single",
      level: greaterRisk(largestAsset?.weightPercent ?? 0, 20, 15),
      title: "단일 종목 집중도",
      metric: largestAsset ? `${largestAsset.name} ${formatPercent(largestAsset.weightPercent)}` : "-",
      detail: largestAsset ? `가장 큰 종목이 총자산의 ${formatPercent(largestAsset.weightPercent)}를 차지합니다.` : "보유 종목 데이터가 없습니다.",
      threshold: "높음 ≥ 20% · 중간 ≥ 15%",
    },
    {
      id: "top-three",
      level: greaterRisk(topThreeWeightPercent, 60, 45),
      title: "상위 3종목 집중도",
      metric: formatPercent(topThreeWeightPercent),
      detail: "상위 3개 종목의 평가액 비중 합계입니다.",
      threshold: "높음 ≥ 60% · 중간 ≥ 45%",
    },
    {
      id: "allocation",
      level: greaterRisk(maxGroupDeviationPercentagePoints ?? 0, 10, 5),
      title: "목표 비중 최대 이탈",
      metric: formatPercentagePoint(maxGroupDeviationPercentagePoints),
      detail: "ISA·코인·현금 중 목표 비중에서 가장 크게 벗어난 값입니다.",
      threshold: "높음 ≥ 10%p · 중간 ≥ 5%p",
    },
    {
      id: "loss",
      level: greaterRisk(lossExposureWeightPercent, 25, 10),
      title: "큰 손실 종목 노출",
      metric: formatPercent(lossExposureWeightPercent),
      detail: "누계 수익률 -20% 이하 종목이 총자산에서 차지하는 비중입니다.",
      threshold: "높음 ≥ 25% · 중간 ≥ 10%",
    },
    {
      id: "data",
      level: providersHealthy ? "low" : "high",
      title: "데이터 신뢰도",
      metric: providersHealthy ? "실제 데이터" : "확인 필요",
      detail: providersHealthy ? "연결된 제공자가 실제 데이터 상태입니다." : "지연·대체값 또는 제공자 오류 상태를 확인해야 합니다.",
      threshold: "실제 데이터·fallback 없음",
    },
    {
      id: "history",
      level: view.performance.status === "provisional" ? "high" : view.performance.status === "insufficient_data" ? "medium" : "low",
      title: "성과 이력 완전성",
      metric: view.performance.status === "insufficient_data" ? "데이터 부족" : view.performance.status === "provisional" ? "잠정" : "확정",
      detail: view.performance.status === "insufficient_data" ? "낙폭과 TWR 판단에 필요한 평가 이력이 더 필요합니다." : "현재 성과 계산 상태를 기준으로 표시합니다.",
      threshold: "확정 성과 이력",
    },
  ];
  checks.sort((left, right) => levelRank[right.level] - levelRank[left.level]);

  const highCount = checks.filter((check) => check.level === "high").length;
  const mediumCount = checks.filter((check) => check.level === "medium").length;

  return {
    highestLevel: highCount ? "high" : mediumCount ? "medium" : "low",
    highCount,
    mediumCount,
    checks,
    largestAsset,
    topThreeWeightPercent,
    lossExposureWeightPercent,
    maxGroupDeviationPercentagePoints,
    maxDrawdownPct: view.performance.maxDrawdownPct,
    concentrationAssets: concentrationAssets.slice(0, 5),
    lossAssets,
    groupDeviations: [...view.groups].sort(
      (left, right) => Math.abs(right.targetDiffPercentagePoints ?? 0) - Math.abs(left.targetDiffPercentagePoints ?? 0),
    ),
  };
}

function greaterRisk(value: number, high: number, medium: number): RiskLevel {
  if (value >= high) return "high";
  if (value >= medium) return "medium";
  return "low";
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function formatPercent(value: number): string {
  return `${value.toFixed(2)}%`;
}

function formatPercentagePoint(value: number | null): string {
  return value === null ? "-" : `${value.toFixed(2)}%p`;
}
