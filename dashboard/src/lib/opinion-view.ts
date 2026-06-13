import type { DashboardView } from "./dashboard-view";
import type { NewsRiskView, NewsRiskViewItem } from "./news-risk-view";
import type { RiskCheck, RiskView } from "./risk-view";

export type OpinionAction = "observe" | "maintain" | "review";
export type OpinionConfidence = "low" | "medium" | "high";

export type OpinionViewItem = {
  id: string;
  title: string;
  action: OpinionAction;
  actionLabel: string;
  confidence: OpinionConfidence;
  confidenceLabel: string;
  summary: string;
  evidence: string[];
  counterEvidence: string[];
  watchIndicators: string[];
  relatedAssets: string[];
  sourceLabels: string[];
};

const actionLabels: Record<OpinionAction, string> = {
  observe: "관찰",
  maintain: "유지",
  review: "재검토",
};
const confidenceLabels: Record<OpinionConfidence, string> = {
  low: "낮음",
  medium: "보통",
  high: "높음",
};
const actionRank: Record<OpinionAction, number> = { review: 3, observe: 2, maintain: 1 };

export function buildOpinionView(
  view: DashboardView,
  risk: RiskView,
  newsRisk: NewsRiskView | null,
): OpinionViewItem[] {
  const numericOpinions = risk.checks
    .filter((check) => check.level !== "low")
    .map((check) => numericOpinion(check, risk));
  const newsOpinions = newsRisk
    ? [...newsRisk.directRisks, ...newsRisk.marketRisks].map(newsOpinion)
    : [];
  const opinions = [...numericOpinions, ...newsOpinions];

  if (!opinions.length) {
    opinions.push({
      id: "portfolio-maintain",
      title: "현재 운용 상태 유지",
      action: "maintain",
      actionLabel: actionLabels.maintain,
      confidence: "medium",
      confidenceLabel: confidenceLabels.medium,
      summary: "현재 수치 위험과 뉴스 위험에서 즉시 재검토가 필요한 신호가 확인되지 않았습니다.",
      evidence: unique([
        `총자산 ${Math.round(view.totalValueKrw).toLocaleString("ko-KR")}원`,
        view.performance.cumulativeTwrPct === null
          ? ""
          : `누적 TWR ${formatPercent(view.performance.cumulativeTwrPct)}`,
      ]),
      counterEvidence: [],
      watchIndicators: ["목표 비중 이탈", "데이터 최신성", "뉴스 기반 잠재 리스크"],
      relatedAssets: [],
      sourceLabels: ["수치 리스크", "뉴스 리스크"],
    });
  }

  return opinions.sort((left, right) => actionRank[right.action] - actionRank[left.action]);
}

function numericOpinion(check: RiskCheck, risk: RiskView): OpinionViewItem {
  const action: OpinionAction = check.level === "high" ? "review" : "observe";
  const confidence: OpinionConfidence = check.level === "high" ? "high" : "medium";
  return {
    id: `numeric-${check.id}`,
    title: check.title,
    action,
    actionLabel: actionLabels[action],
    confidence,
    confidenceLabel: confidenceLabels[confidence],
    summary: check.detail,
    evidence: unique([check.metric, check.detail]),
    counterEvidence: [],
    watchIndicators: unique([check.threshold]),
    relatedAssets: numericRelatedAssets(check, risk),
    sourceLabels: ["수치 리스크"],
  };
}

function newsOpinion(item: NewsRiskViewItem): OpinionViewItem {
  const action: OpinionAction = item.priority === "urgent" ? "review" : "observe";
  const confidence: OpinionConfidence =
    item.priority === "urgent" ? "high" : item.priority === "caution" ? "medium" : "low";
  return {
    id: `news-${item.id}`,
    title: item.title,
    action,
    actionLabel: actionLabels[action],
    confidence,
    confidenceLabel: confidenceLabels[confidence],
    summary: item.potential_impact,
    evidence: unique([...item.facts, item.transmission_path]),
    counterEvidence: unique(item.counter_evidence),
    watchIndicators: unique(item.watch_indicators),
    relatedAssets: unique(item.related_assets),
    sourceLabels: unique(item.sourceLabels),
  };
}

function numericRelatedAssets(check: RiskCheck, risk: RiskView): string[] {
  if (check.id === "single") return unique([risk.largestAsset?.name ?? ""]);
  if (check.id === "top-three") return unique(risk.concentrationAssets.slice(0, 3).map((asset) => asset.name));
  if (check.id === "loss") return unique(risk.lossAssets.map((asset) => asset.name));
  if (check.id === "allocation") {
    return unique(
      risk.groupDeviations
        .filter((group) => Math.abs(group.targetDiffPercentagePoints ?? 0) >= 5)
        .map((group) => group.label),
    );
  }
  return [];
}

function unique(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}

function formatPercent(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}
