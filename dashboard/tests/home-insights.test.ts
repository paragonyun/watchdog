import assert from "node:assert/strict";
import test from "node:test";

import { buildHomeInsights } from "../src/lib/home-insights";
import type { CalendarPayload } from "../src/lib/calendar-payload";
import type { NewsRiskItem, NewsRiskPayload } from "../src/lib/news-risk-payload";
import type { OpinionPayload } from "../src/lib/opinion-payload";
import type { ResearchReportPayload } from "../src/lib/report-payload";

function risk(overrides: Partial<NewsRiskItem>): NewsRiskItem {
  return {
    risk_id: "risk-1",
    scope: "direct",
    priority: "watch",
    title: "시장 변동성 확대",
    category: "유동성",
    source_type: ["rss_rule"],
    facts: ["시장 변동성이 확대되었습니다."],
    potential_impact: "관련 자산 가격 변동성이 커질 수 있습니다.",
    transmission_path: "유동성 축소 -> 가격 변동성 확대",
    related_assets: ["BTC"],
    related_asset_groups: ["coin"],
    related_asset_weight_pct: 10,
    watch_indicators: ["거래량"],
    counter_evidence: ["자금 유입 회복"],
    priority_reasons: ["관련 자산 비중"],
    source_links: [{ title: "기사", url: "https://example.com/news" }],
    first_seen_at: "2026-06-15T00:00:00+00:00",
    last_updated_at: "2026-06-15T01:00:00+00:00",
    freshness: "active",
    change_reason: null,
    ...overrides,
  };
}

const newsRisk: NewsRiskPayload = {
  schema_version: "news_risk_payload_v1",
  generated_at: "2026-06-15T09:00:00+00:00",
  lookback_hours: 72,
  rss_generated_at: "2026-06-15T09:00:00+00:00",
  codex_generated_at: "2026-06-15T08:00:00+00:00",
  status: "actual",
  direct_risks: [
    risk({ risk_id: "watch", title: "관찰 위험" }),
    risk({ risk_id: "urgent", title: "긴급 위험", priority: "urgent", freshness: "new" }),
  ],
  market_risks: [
    risk({
      risk_id: "market",
      scope: "market",
      title: "시장 위험",
      priority: "caution",
      related_assets: [],
      related_asset_groups: ["isa", "coin"],
    }),
  ],
};

const opinion: OpinionPayload = {
  schema_version: "dashboard_opinion_v1",
  opinion_id: "opinion-20260615-0900",
  generated_at: "2026-06-15T09:00:00+00:00",
  portfolio_posture: "observe",
  summary: "매도 대상 위험을 먼저 줄이고 매수 후보는 가격 조건을 확인합니다.",
  items: [
    {
      id: "btc",
      symbol: "BTC",
      name: "비트코인",
      action: "observe",
      confidence: "medium",
      thesis: "유동성을 확인합니다.",
      evidence: [],
      counter_evidence: [],
      catalysts: [],
      invalidation_conditions: [],
      suggested_position_note: "현 비중 유지",
      sources: [{ label: "Codex", url: null }],
    },
    {
      id: "arb",
      symbol: "ARB",
      name: "아비트럼",
      action: "sell",
      confidence: "high",
      thesis: "투자 논리가 약화됐습니다.",
      evidence: [],
      counter_evidence: [],
      catalysts: [],
      invalidation_conditions: [],
      suggested_position_note: "위험 축소",
      sources: [{ label: "Codex", url: null }],
    },
    {
      id: "spy",
      symbol: "SPY",
      name: "S&P500",
      action: "buy",
      confidence: "medium",
      thesis: "장기 분산 효과가 유효합니다.",
      evidence: [],
      counter_evidence: [],
      catalysts: [],
      invalidation_conditions: [],
      suggested_position_note: "분할 접근",
      sources: [{ label: "Codex", url: null }],
    },
  ],
  disclaimer: "투자 자문이 아닙니다.",
};

const report: ResearchReportPayload = {
  schema_version: "dashboard_report_v2",
  report_id: "weekly-20260615-0900",
  generated_at: "2026-06-15T09:00:00+00:00",
  report_kind: "weekly",
  title: "주간 포트폴리오 전략",
  subtitle: "위험 축소와 선별 매수",
  document_status: "final",
  stance: "cautious",
  summary: { total_value_krw: 1000, change_krw: 10, change_pct: 1, validation_valid: true },
  executive_summary: ["고위험 알트코인 노출을 축소합니다.", "현금 완충력을 유지합니다."],
  key_metrics: [{ label: "누적 TWR", value: "+3.0%", context: "확정", tone: "positive" }],
  investment_thesis: {
    headline: "질 좋은 위험만 보유합니다.",
    body: "핵심 자산과 현금 완충력을 유지합니다.",
    facts: ["ISA 비중이 가장 큽니다."],
    interpretations: ["변동성 확대 가능성이 있습니다."],
    estimates: ["현금이 낙폭을 완충할 수 있습니다."],
  },
  asset_views: [
    {
      symbol: "SPY",
      name: "S&P500",
      action: "buy",
      thesis: "장기 분산 효과",
      catalysts: ["금리 안정"],
      risks: ["경기 둔화"],
    },
  ],
  scenarios: [{ name: "기준", probability: "중간", trigger: "금리 안정", impact: "완만한 회복", response: "현 비중 유지" }],
  risk_watchlist: ["유동성 축소"],
  conclusion: "위험 예산을 지키며 선별적으로 대응합니다.",
  appendix: {
    asset_groups: { coin: 200, equity: 700, cash: 100 },
    assets: [],
    provider_status: [],
    validation_issues: [],
  },
};

const previousOpinion: OpinionPayload = {
  ...opinion,
  opinion_id: "opinion-20260608-0900",
  generated_at: "2026-06-08T09:00:00+00:00",
  items: opinion.items.map((item) => item.id === "arb" ? { ...item, action: "observe" } : item),
};

const previousReport: ResearchReportPayload = {
  ...report,
  report_id: "weekly-20260608-0900",
  generated_at: "2026-06-08T09:00:00+00:00",
  stance: "neutral",
  asset_views: report.asset_views.map((item) => ({ ...item, action: "observe" })),
};

const calendar: CalendarPayload = {
  schema_version: "dashboard_calendar_v1",
  generated_at: "2026-06-18T08:00:00+09:00",
  source: "codex",
  timezone: "Asia/Seoul",
  events: [
    {
      id: "past",
      title: "지난 일정",
      starts_at: "2026-06-17T09:00:00+09:00",
      country: "미국",
      category: "경기",
      importance: "high",
      asset_groups: ["isa"],
      expected_impact: "이미 지난 일정입니다.",
      watch_note: "표시하지 않습니다.",
      source_url: null,
    },
    {
      id: "cpi",
      title: "미국 CPI",
      starts_at: "2026-06-19T21:30:00+09:00",
      country: "미국",
      category: "물가",
      importance: "high",
      asset_groups: ["isa", "coin"],
      expected_impact: "인플레이션 경로에 따라 주식과 코인의 할인율 부담이 달라질 수 있습니다.",
      watch_note: "근원 CPI와 서비스 물가를 확인합니다.",
      source_url: "https://example.com/cpi",
    },
  ],
};

test("home insights prioritize urgent risks and summarize Codex opinions", () => {
  const result = buildHomeInsights({ opinion, newsRisk, report });

  assert.equal(result.newsRisk?.totalCount, 3);
  assert.equal(result.newsRisk?.newCount, 1);
  assert.deepEqual(result.newsRisk?.items.map((item) => item.title), ["긴급 위험", "시장 위험", "관찰 위험"]);
  assert.deepEqual(result.opinion?.counts, { buy: 1, sell: 1, observe: 1 });
  assert.deepEqual(result.opinion?.items.map((item) => item.action), ["sell", "buy", "observe"]);
  assert.equal(result.opinion?.postureLabel, "관찰 필요");
});

test("home insights expose the latest completed report thesis", () => {
  const result = buildHomeInsights({ opinion, newsRisk, report });

  assert.equal(result.report?.kindLabel, "주간 리포트");
  assert.equal(result.report?.stanceLabel, "신중");
  assert.equal(result.report?.headline, "질 좋은 위험만 보유합니다.");
  assert.deepEqual(result.report?.summaryPoints, report.executive_summary);
  assert.equal(result.report?.validationValid, true);
});

test("home insights keep unavailable sources empty", () => {
  const result = buildHomeInsights({});

  assert.equal(result.opinion, null);
  assert.equal(result.newsRisk, null);
  assert.equal(result.report, null);
  assert.equal(result.calendar, null);
});

test("home insights show upcoming calendar events and previous judgment changes", () => {
  const result = buildHomeInsights({
    opinion,
    previousOpinion,
    newsRisk,
    report,
    previousReport,
    calendar,
    now: new Date("2026-06-18T09:00:00+09:00"),
  });

  assert.equal(result.calendar?.totalCount, 1);
  assert.equal(result.calendar?.highCount, 1);
  assert.deepEqual(result.calendar?.items.map((item) => item.title), ["미국 CPI"]);
  assert.equal(result.calendar?.items[0].importanceLabel, "높음");
  assert.equal(result.opinion?.changeSummary, "아비트럼: 관찰 필요 → 매도");
  assert.equal(result.report?.changeSummary, "전략 판단: 중립 → 신중");
});
