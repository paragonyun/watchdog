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

export type NewsRiskNarrative = {
  tone: NewsRiskPriority;
  headline: string;
  primaryRiskTitle: string | null;
  summary: string;
  nextActions: string[];
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
  narrative: NewsRiskNarrative;
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
    narrative: buildNarrative(directRisks, marketRisks, payload.status),
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

function buildNarrative(
  directRisks: NewsRiskViewItem[],
  marketRisks: NewsRiskViewItem[],
  status: NewsRiskStatus,
): NewsRiskNarrative {
  const primary = [...directRisks, ...marketRisks].sort(compareRisks)[0] ?? null;
  if (!primary) {
    return {
      tone: "watch",
      headline: "새로 확인된 뉴스 리스크는 제한적입니다.",
      primaryRiskTitle: null,
      summary: "현재 업로드된 뉴스 리스크 기준으로 보유 자산에 직접 연결되는 우선 확인 이슈는 없습니다.",
      nextActions: ["다음 자동 갱신 전까지 기존 가격, 환율, 금리 지표를 유지 관찰합니다."],
    };
  }

  const target = primary.related_assets.length
    ? primary.related_assets.join(", ")
    : groupLabels(primary.related_asset_groups);
  const refreshNote =
    status !== "actual" || primary.freshness === "refresh_required"
      ? " 최신성 재확인이 필요합니다."
      : "";

  return {
    tone: primary.priority,
    headline: headlineFor(primary, status),
    primaryRiskTitle: primary.title,
    summary: `${primary.title} 이슈가 ${target}에 연결되어 있고 현재 관련 노출은 ${formatPercent(primary.related_asset_weight_pct)}입니다. ${primary.potential_impact}${refreshNote}`,
    nextActions: unique([
      ...primary.watch_indicators.slice(0, 2).map((item) => `관찰 지표: ${item}`),
      ...primary.counter_evidence.slice(0, 1).map((item) => `반대 근거: ${item}`),
      ...primary.priority_reasons.slice(0, 1).map((item) => `우선순위 근거: ${item}`),
    ]),
  };
}

function headlineFor(primary: NewsRiskViewItem, status: NewsRiskStatus): string {
  if (status !== "actual" || primary.freshness === "refresh_required") {
    return "뉴스 리스크 재확인이 필요합니다.";
  }
  if (primary.priority === "urgent") return "즉시 확인할 뉴스 리스크가 있습니다.";
  if (primary.priority === "caution") return "주의 깊게 볼 뉴스 흐름이 있습니다.";
  return "관찰할 뉴스 흐름이 있습니다.";
}

function groupLabels(groups: Array<"isa" | "coin" | "cash">): string {
  const labels = { isa: "ISA", coin: "코인", cash: "현금" };
  return groups.map((group) => labels[group]).join(", ");
}

function formatPercent(value: number): string {
  return `${value.toFixed(2)}%`;
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter((value) => value.trim().length > 0)));
}

