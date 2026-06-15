import type { NewsRiskPayload, NewsRiskPriority } from "./news-risk-payload";
import { buildNewsRiskView } from "./news-risk-view";
import type { OpinionAction, OpinionPayload } from "./opinion-payload";
import { isResearchReport, type ReportPayload, type ResearchReportPayload } from "./report-payload";

export type HomeInsights = {
  newsRisk: {
    generatedAt: string;
    statusLabel: string;
    totalCount: number;
    newCount: number;
    items: Array<{
      id: string;
      priority: NewsRiskPriority;
      priorityLabel: string;
      title: string;
      impact: string;
    }>;
  } | null;
  opinion: {
    generatedAt: string;
    posture: OpinionAction;
    postureLabel: string;
    summary: string;
    counts: Record<OpinionAction, number>;
    items: Array<{
      id: string;
      name: string;
      symbol: string;
      action: OpinionAction;
      actionLabel: string;
      thesis: string;
    }>;
  } | null;
  report: {
    id: string;
    generatedAt: string;
    title: string;
    kindLabel: string;
    stance: ResearchReportPayload["stance"] | null;
    stanceLabel: string;
    headline: string;
    summaryPoints: string[];
    validationValid: boolean;
  } | null;
};

const opinionRank: Record<OpinionAction, number> = { sell: 3, buy: 2, observe: 1 };
const newsRiskRank: Record<NewsRiskPriority, number> = { urgent: 3, caution: 2, watch: 1 };

export function buildHomeInsights(
  opinion: OpinionPayload | null,
  newsRisk: NewsRiskPayload | null,
  report: ReportPayload | null,
): HomeInsights {
  return {
    newsRisk: newsRisk ? newsRiskSummary(newsRisk) : null,
    opinion: opinion ? opinionSummary(opinion) : null,
    report: report ? reportSummary(report) : null,
  };
}

function newsRiskSummary(payload: NewsRiskPayload): NonNullable<HomeInsights["newsRisk"]> {
  const view = buildNewsRiskView(payload);
  return {
    generatedAt: view.generatedAt,
    statusLabel: view.statusLabel,
    totalCount: view.directCount + view.marketCount,
    newCount: view.newCount,
    items: [...view.directRisks, ...view.marketRisks]
      .sort((left, right) => newsRiskRank[right.priority] - newsRiskRank[left.priority])
      .slice(0, 3)
      .map((item) => ({
        id: item.id,
        priority: item.priority,
        priorityLabel: item.priorityLabel,
        title: item.title,
        impact: item.potential_impact,
      })),
  };
}

function opinionSummary(payload: OpinionPayload): NonNullable<HomeInsights["opinion"]> {
  const counts = { buy: 0, sell: 0, observe: 0 };
  payload.items.forEach((item) => counts[item.action] += 1);
  return {
    generatedAt: payload.generated_at,
    posture: payload.portfolio_posture,
    postureLabel: actionLabel(payload.portfolio_posture),
    summary: payload.summary,
    counts,
    items: [...payload.items]
      .sort((left, right) => opinionRank[right.action] - opinionRank[left.action])
      .slice(0, 3)
      .map((item) => ({
        id: item.id,
        name: item.name,
        symbol: item.symbol,
        action: item.action,
        actionLabel: actionLabel(item.action),
        thesis: item.thesis,
      })),
  };
}

function reportSummary(payload: ReportPayload): NonNullable<HomeInsights["report"]> {
  if (isResearchReport(payload)) {
    return {
      id: payload.report_id,
      generatedAt: payload.generated_at,
      title: payload.title,
      kindLabel: kindLabel(payload.report_kind),
      stance: payload.stance,
      stanceLabel: stanceLabel(payload.stance),
      headline: payload.investment_thesis.headline,
      summaryPoints: payload.executive_summary.slice(0, 3),
      validationValid: payload.summary.validation_valid,
    };
  }
  return {
    id: payload.report_id,
    generatedAt: payload.generated_at,
    title: payload.title,
    kindLabel: kindLabel(payload.report_kind),
    stance: null,
    stanceLabel: "작성 원본",
    headline: payload.sections[0]?.title ?? payload.title,
    summaryPoints: payload.sections[0]?.lines.slice(0, 3) ?? [],
    validationValid: payload.summary.validation_valid,
  };
}

function actionLabel(action: OpinionAction): string {
  return action === "buy" ? "매수" : action === "sell" ? "매도" : "관찰 필요";
}

function kindLabel(kind: ReportPayload["report_kind"]): string {
  return kind === "weekly" ? "주간 리포트" : "포트폴리오 리포트";
}

function stanceLabel(stance: ResearchReportPayload["stance"]): string {
  return stance === "positive" ? "긍정적" : stance === "cautious" ? "신중" : "중립";
}
