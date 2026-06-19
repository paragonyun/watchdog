import assert from "node:assert/strict";
import test from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DashboardHome } from "../src/app/dashboard/page";
import type { DashboardView } from "../src/lib/dashboard-view";
import type { HomeInsights } from "../src/lib/home-insights";

const view: DashboardView = {
  generatedAt: "2026-06-19T18:00:00+09:00",
  totalValueKrw: 69720436,
  status: "actual",
  lastActualAt: "2026-06-19T18:00:00+09:00",
  periodChange: { changeKrw: 120000, changePct: 0.17 },
  performance: {
    cumulativeTwrPct: 8.4,
    monthTwrPct: 2.1,
    benchmarkReturnPct: 4.21,
    excessReturnPct: 4.19,
    maxDrawdownPct: -3.2,
    status: "confirmed",
  },
  groups: [
    { key: "isa", label: "ISA", valueKrw: 50545825, weightPercent: 72.5, targetWeightPercent: 70, targetDiffPercentagePoints: 2.5 },
    { key: "coin", label: "코인", valueKrw: 11112128, weightPercent: 15.94, targetWeightPercent: 20, targetDiffPercentagePoints: -4.06 },
    { key: "cash", label: "현금 및 예수금", valueKrw: 8062483, weightPercent: 11.56, targetWeightPercent: 10, targetDiffPercentagePoints: 1.56 },
  ],
  assets: [
    {
      symbol: "TIGER_SP500",
      name: "S&P500",
      assetType: "isa",
      valueKrw: 12824800,
      weightPercent: 18.4,
      profitLossRatePercent: 25.75,
      targetDiffPercentagePoints: null,
      priceSource: "kis",
    },
  ],
  news: [
    {
      title: "미국 증시 기술주 강세",
      impact: "긍정",
      impact_score: 2,
      score_label: "규칙 기반",
      related_assets: ["TIGER_SP500"],
      reason: "ISA 주식형 ETF에 우호적인 흐름입니다.",
      why_it_matters: "주요 보유자산과 연결됩니다.",
    },
  ],
  attention: [{ level: "medium", title: "성과 수치 잠정 상태", detail: "거래 내역 대사 후 확정됩니다." }],
  opinions: [],
  calendar: [],
  reports: [],
  providers: [{ provider: "kis", status: "actual", usedFallback: false }],
};

const insights: HomeInsights = {
  calendar: null,
  newsRisk: null,
  opinion: null,
  report: null,
};

test("dashboard home renders the approved A terminal structure", () => {
  const html = renderToStaticMarkup(createElement(DashboardHome, { view, insights }));

  assert.match(html, /dashboard-terminal/);
  assert.match(html, /terminal-kpi-strip/);
  assert.match(html, /투자 성과 \(TWR\)/);
  assert.match(html, /자산 배분/);
  assert.match(html, /주요 촉매 일정/);
  assert.match(html, /최신 리서치/);
});
