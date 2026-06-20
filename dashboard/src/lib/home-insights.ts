import type { CalendarImportance, CalendarPayload } from "./calendar-payload";
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
      sourceTitle: string | null;
      sourceUrl: string | null;
      publishedAt: string;
    }>;
  } | null;
  calendar: {
    generatedAt: string;
    totalCount: number;
    highCount: number;
    items: Array<{
      id: string;
      title: string;
      startsAt: string;
      country: string;
      category: string;
      importance: CalendarImportance;
      importanceLabel: string;
      expectedImpact: string;
      watchNote: string;
    }>;
  } | null;
  opinion: {
    generatedAt: string;
    posture: OpinionAction;
    postureLabel: string;
    summary: string;
    changeSummary: string | null;
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
    changeSummary: string | null;
    validationValid: boolean;
  } | null;
};

export type BuildHomeInsightsInput = {
  opinion?: OpinionPayload | null;
  previousOpinion?: OpinionPayload | null;
  newsRisk?: NewsRiskPayload | null;
  report?: ReportPayload | null;
  previousReport?: ReportPayload | null;
  calendar?: CalendarPayload | null;
  now?: Date;
};

const opinionRank: Record<OpinionAction, number> = { sell: 3, buy: 2, observe: 1 };
const newsRiskRank: Record<NewsRiskPriority, number> = { urgent: 3, caution: 2, watch: 1 };
const importanceLabels: Record<CalendarImportance, string> = { high: "높음", medium: "중간", low: "낮음" };

export function buildHomeInsights(input: BuildHomeInsightsInput = {}): HomeInsights {
  return {
    newsRisk: input.newsRisk ? newsRiskSummary(input.newsRisk) : null,
    calendar: input.calendar ? calendarSummary(input.calendar, input.now ?? new Date()) : null,
    opinion: input.opinion ? opinionSummary(input.opinion, input.previousOpinion ?? null) : null,
    report: input.report ? reportSummary(input.report, input.previousReport ?? null) : null,
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
        sourceTitle: item.source_links[0]?.title ?? null,
        sourceUrl: item.source_links[0]?.url ?? null,
        publishedAt: item.last_updated_at,
      })),
  };
}

function calendarSummary(payload: CalendarPayload, now: Date): NonNullable<HomeInsights["calendar"]> {
  const upcoming = payload.events
    .filter((event) => Date.parse(event.starts_at) >= now.getTime())
    .sort((left, right) => Date.parse(left.starts_at) - Date.parse(right.starts_at));
  return {
    generatedAt: payload.generated_at,
    totalCount: upcoming.length,
    highCount: upcoming.filter((event) => event.importance === "high").length,
    items: upcoming.slice(0, 3).map((event) => ({
      id: event.id,
      title: event.title,
      startsAt: event.starts_at,
      country: event.country,
      category: event.category,
      importance: event.importance,
      importanceLabel: importanceLabels[event.importance],
      expectedImpact: event.expected_impact,
      watchNote: event.watch_note,
    })),
  };
}

function opinionSummary(payload: OpinionPayload, previous: OpinionPayload | null): NonNullable<HomeInsights["opinion"]> {
  const counts = { buy: 0, sell: 0, observe: 0 };
  payload.items.forEach((item) => counts[item.action] += 1);
  return {
    generatedAt: payload.generated_at,
    posture: payload.portfolio_posture,
    postureLabel: actionLabel(payload.portfolio_posture),
    summary: payload.summary,
    changeSummary: opinionChangeSummary(payload, previous),
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

function reportSummary(payload: ReportPayload, previous: ReportPayload | null): NonNullable<HomeInsights["report"]> {
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
      changeSummary: reportChangeSummary(payload, previous),
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
    changeSummary: null,
    validationValid: payload.summary.validation_valid,
  };
}

function opinionChangeSummary(payload: OpinionPayload, previous: OpinionPayload | null): string | null {
  if (!previous) return null;
  const previousById = new Map(previous.items.map((item) => [item.id, item]));
  for (const item of payload.items) {
    const before = previousById.get(item.id);
    if (before && before.action !== item.action) {
      return `${item.name}: ${actionLabel(before.action)} → ${actionLabel(item.action)}`;
    }
  }
  if (previous.portfolio_posture !== payload.portfolio_posture) {
    return `포트폴리오 판단: ${actionLabel(previous.portfolio_posture)} → ${actionLabel(payload.portfolio_posture)}`;
  }
  return null;
}

function reportChangeSummary(payload: ResearchReportPayload, previous: ReportPayload | null): string | null {
  if (!previous || !isResearchReport(previous)) return null;
  if (previous.stance !== payload.stance) {
    return `전략 판단: ${stanceLabel(previous.stance)} → ${stanceLabel(payload.stance)}`;
  }
  const previousBySymbol = new Map(previous.asset_views.map((item) => [item.symbol, item]));
  for (const item of payload.asset_views) {
    const before = previousBySymbol.get(item.symbol);
    if (before && before.action !== item.action) {
      return `${item.name}: ${actionLabel(before.action)} → ${actionLabel(item.action)}`;
    }
  }
  return null;
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
