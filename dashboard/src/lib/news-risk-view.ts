import type {
  NewsRiskFreshness,
  NewsRiskItem,
  NewsRiskPayload,
  NewsRiskPriority,
  NewsRiskStatus,
} from "./news-risk-payload";

export type NewsRiskViewItem = NewsRiskItem & {
  id: string;
  priorityLabel: string;
  freshnessLabel: string;
  sourceLabels: string[];
};

export type NewsRiskView = {
  status: NewsRiskStatus;
  statusLabel: string;
  generatedAt: string;
  codexGeneratedAt: string | null;
  directRisks: NewsRiskViewItem[];
  marketRisks: NewsRiskViewItem[];
  directCount: number;
  marketCount: number;
  newCount: number;
  needsRefresh: boolean;
};

const priorityRank: Record<NewsRiskPriority, number> = { urgent: 3, caution: 2, watch: 1 };
const freshnessRank: Record<NewsRiskFreshness, number> = { new: 3, active: 2, refresh_required: 1 };
const priorityLabels: Record<NewsRiskPriority, string> = { urgent: "긴급", caution: "주의", watch: "관찰" };
const freshnessLabels: Record<NewsRiskFreshness, string> = {
  new: "신규",
  active: "진행 중",
  refresh_required: "재확인 필요",
};
const statusLabels: Record<NewsRiskStatus, string> = {
  actual: "최신",
  delayed: "지연",
  refresh_required: "재확인 필요",
};
const sourceLabels = { rss_rule: "RSS 규칙", codex_research: "Codex 심층 분석" } as const;

export function buildNewsRiskView(payload: NewsRiskPayload): NewsRiskView {
  const directRisks = payload.direct_risks.map(toViewItem).sort(compareRisks);
  const marketRisks = payload.market_risks.map(toViewItem).sort(compareRisks);
  const allRisks = [...directRisks, ...marketRisks];

  return {
    status: payload.status,
    statusLabel: statusLabels[payload.status],
    generatedAt: payload.generated_at,
    codexGeneratedAt: payload.codex_generated_at,
    directRisks,
    marketRisks,
    directCount: directRisks.length,
    marketCount: marketRisks.length,
    newCount: allRisks.filter((risk) => risk.freshness === "new").length,
    needsRefresh: payload.status !== "actual" || allRisks.some((risk) => risk.freshness === "refresh_required"),
  };
}

function toViewItem(item: NewsRiskItem): NewsRiskViewItem {
  return {
    ...item,
    id: item.risk_id,
    priorityLabel: priorityLabels[item.priority],
    freshnessLabel: freshnessLabels[item.freshness],
    sourceLabels: item.source_type.map((source) => sourceLabels[source]),
  };
}

function compareRisks(left: NewsRiskViewItem, right: NewsRiskViewItem): number {
  return (
    priorityRank[right.priority] - priorityRank[left.priority] ||
    freshnessRank[right.freshness] - freshnessRank[left.freshness] ||
    right.related_asset_weight_pct - left.related_asset_weight_pct
  );
}

