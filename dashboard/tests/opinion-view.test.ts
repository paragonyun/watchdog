import assert from "node:assert/strict";
import test from "node:test";

import type { DashboardView } from "../src/lib/dashboard-view";
import type { NewsRiskView } from "../src/lib/news-risk-view";
import { buildOpinionView } from "../src/lib/opinion-view";
import { buildRiskView } from "../src/lib/risk-view";

function dashboardView(overrides: Partial<DashboardView> = {}): DashboardView {
  return {
    generatedAt: "2026-06-13T09:00:00+00:00",
    totalValueKrw: 100,
    status: "actual",
    lastActualAt: "2026-06-13T09:00:00+00:00",
    periodChange: { changeKrw: 0, changePct: 0 },
    performance: {
      cumulativeTwrPct: 5,
      monthTwrPct: 1,
      benchmarkReturnPct: 3,
      excessReturnPct: 2,
      maxDrawdownPct: -4,
      status: "confirmed",
    },
    groups: [
      { key: "isa", label: "ISA", valueKrw: 50, weightPercent: 50, targetWeightPercent: 50, targetDiffPercentagePoints: 0 },
      { key: "coin", label: "코인", valueKrw: 20, weightPercent: 20, targetWeightPercent: 20, targetDiffPercentagePoints: 0 },
      { key: "cash", label: "현금 및 예수금", valueKrw: 30, weightPercent: 30, targetWeightPercent: 30, targetDiffPercentagePoints: 0 },
    ],
    assets: [
      { symbol: "A", name: "A", assetType: "isa", valueKrw: 10, weightPercent: 10, profitLossRatePercent: 3, targetDiffPercentagePoints: null, priceSource: "kis" },
      { symbol: "B", name: "B", assetType: "isa", valueKrw: 10, weightPercent: 10, profitLossRatePercent: 2, targetDiffPercentagePoints: null, priceSource: "kis" },
      { symbol: "C", name: "C", assetType: "coin", valueKrw: 10, weightPercent: 10, profitLossRatePercent: 1, targetDiffPercentagePoints: null, priceSource: "upbit" },
      { symbol: "D", name: "D", assetType: "isa", valueKrw: 10, weightPercent: 10, profitLossRatePercent: 0, targetDiffPercentagePoints: null, priceSource: "kis" },
    ],
    news: [],
    attention: [],
    opinions: [],
    calendar: [],
    reports: [],
    providers: [
      { provider: "kis", status: "actual", usedFallback: false },
      { provider: "upbit", status: "actual", usedFallback: false },
    ],
    ...overrides,
  };
}

function newsRiskView(): NewsRiskView {
  return {
    status: "actual",
    statusLabel: "최신",
    generatedAt: "2026-06-13T09:00:00+00:00",
    codexGeneratedAt: "2026-06-13T08:00:00+00:00",
    directCount: 1,
    marketCount: 0,
    newCount: 1,
    needsRefresh: false,
    marketRisks: [],
    directRisks: [
      {
        risk_id: "btc-liquidity",
        id: "btc-liquidity",
        scope: "direct",
        priority: "urgent",
        priorityLabel: "긴급",
        title: "비트코인 유동성 위험",
        category: "유동성",
        source_type: ["rss_rule", "codex_research"],
        sourceLabels: ["RSS 규칙", "Codex 심층 분석"],
        facts: ["거래량이 감소했습니다.", "거래량이 감소했습니다.", ""],
        potential_impact: "가격 변동성이 확대될 수 있습니다.",
        transmission_path: "유동성 축소 -> 가격 변동성 확대",
        related_assets: ["BTC", "BTC", ""],
        related_asset_groups: ["coin"],
        related_asset_weight_pct: 20,
        watch_indicators: ["거래량", "거래량", ""],
        counter_evidence: ["현물 ETF 자금 유입", ""],
        priority_reasons: ["보유 비중이 큽니다."],
        source_links: [],
        first_seen_at: "2026-06-13T07:00:00+00:00",
        last_updated_at: "2026-06-13T09:00:00+00:00",
        freshness: "new",
        freshnessLabel: "신규",
        change_reason: null,
      },
    ],
  };
}

test("maps high numeric risks to review opinions", () => {
  const view = dashboardView({
    assets: [
      { symbol: "A", name: "집중 종목", assetType: "isa", valueKrw: 30, weightPercent: 30, profitLossRatePercent: 2, targetDiffPercentagePoints: null, priceSource: "kis" },
      { symbol: "B", name: "B", assetType: "coin", valueKrw: 20, weightPercent: 20, profitLossRatePercent: 1, targetDiffPercentagePoints: null, priceSource: "upbit" },
      { symbol: "C", name: "C", assetType: "isa", valueKrw: 15, weightPercent: 15, profitLossRatePercent: 0, targetDiffPercentagePoints: null, priceSource: "kis" },
    ],
  });

  const opinions = buildOpinionView(view, buildRiskView(view), null);
  const concentration = opinions.find((item) => item.id === "numeric-single");

  assert.equal(concentration?.action, "review");
  assert.equal(concentration?.confidence, "high");
  assert.deepEqual(concentration?.relatedAssets, ["집중 종목"]);
  assert.ok(concentration?.evidence.some((item) => item.includes("30.00%")));
});

test("preserves explainable urgent news evidence without duplicates", () => {
  const view = dashboardView();
  const opinions = buildOpinionView(view, buildRiskView(view), newsRiskView());
  const opinion = opinions.find((item) => item.id === "news-btc-liquidity");

  assert.equal(opinion?.action, "review");
  assert.equal(opinion?.confidence, "high");
  assert.deepEqual(opinion?.evidence, ["거래량이 감소했습니다.", "유동성 축소 -> 가격 변동성 확대"]);
  assert.deepEqual(opinion?.counterEvidence, ["현물 ETF 자금 유입"]);
  assert.deepEqual(opinion?.watchIndicators, ["거래량"]);
  assert.deepEqual(opinion?.relatedAssets, ["BTC"]);
  assert.deepEqual(opinion?.sourceLabels, ["RSS 규칙", "Codex 심층 분석"]);
});

test("maps medium risks to observe and creates maintain summary when risks are low", () => {
  const mediumView = dashboardView({
    assets: [
      { symbol: "A", name: "관찰 종목", assetType: "isa", valueKrw: 16, weightPercent: 16, profitLossRatePercent: 2, targetDiffPercentagePoints: null, priceSource: "kis" },
      { symbol: "B", name: "B", assetType: "coin", valueKrw: 10, weightPercent: 10, profitLossRatePercent: 1, targetDiffPercentagePoints: null, priceSource: "upbit" },
      { symbol: "C", name: "C", assetType: "isa", valueKrw: 10, weightPercent: 10, profitLossRatePercent: 0, targetDiffPercentagePoints: null, priceSource: "kis" },
    ],
  });
  const observed = buildOpinionView(mediumView, buildRiskView(mediumView), null);
  assert.equal(observed.find((item) => item.id === "numeric-single")?.action, "observe");

  const maintained = buildOpinionView(dashboardView(), buildRiskView(dashboardView()), null);
  assert.equal(maintained.length, 1);
  assert.equal(maintained[0].action, "maintain");
  assert.doesNotMatch(JSON.stringify(maintained), /매수|매도/);
});
