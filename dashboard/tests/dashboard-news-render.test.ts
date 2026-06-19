import assert from "node:assert/strict";
import test from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DashboardHome } from "../src/app/dashboard/page";
import type { DashboardView } from "../src/lib/dashboard-view";
import type { HomeInsights } from "../src/lib/home-insights";

const baseView: DashboardView = {
  generatedAt: "2026-06-19T18:00:00+09:00",
  totalValueKrw: 69_720_436,
  status: "actual",
  lastActualAt: "2026-06-19T18:00:00+09:00",
  periodChange: { changeKrw: 120_000, changePct: 0.17 },
  performance: {
    cumulativeTwrPct: 8.4,
    monthTwrPct: 2.1,
    benchmarkReturnPct: 4.21,
    excessReturnPct: 4.19,
    maxDrawdownPct: -3.2,
    status: "confirmed",
  },
  groups: [
    { key: "isa", label: "ISA", valueKrw: 50_545_825, weightPercent: 72.5, targetWeightPercent: 70, targetDiffPercentagePoints: 2.5 },
    { key: "coin", label: "Coin", valueKrw: 11_112_128, weightPercent: 15.94, targetWeightPercent: 20, targetDiffPercentagePoints: -4.06 },
    { key: "cash", label: "Cash", valueKrw: 8_062_483, weightPercent: 11.56, targetWeightPercent: 10, targetDiffPercentagePoints: 1.56 },
  ],
  assets: [],
  news: [],
  attention: [],
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

test("dashboard news links to source and sorts by latest date then impact", () => {
  const html = renderToStaticMarkup(createElement(DashboardHome, {
    view: {
      ...baseView,
      news: [
        {
          title: "Older high impact",
          impact: "positive",
          impact_score: 5,
          score_label: "high",
          related_assets: ["BTC"],
          reason: "Older item should not appear first.",
          why_it_matters: "",
          url: "https://example.com/older",
          published_at: "2026-06-18T09:00:00+09:00",
        },
        {
          title: "Latest low impact",
          impact: "negative",
          impact_score: -1,
          score_label: "low",
          related_assets: ["SPY"],
          reason: "Latest item should appear after the same-date higher impact item.",
          why_it_matters: "",
          url: "https://example.com/latest",
          published_at: "2026-06-19T09:00:00+09:00",
        },
        {
          title: "Same day higher impact",
          impact: "positive",
          impact_score: 3,
          score_label: "medium",
          related_assets: ["QQQ"],
          reason: "Higher impact should win same-day ordering.",
          why_it_matters: "",
          url: "https://example.com/same-day-high",
          published_at: "2026-06-19T09:00:00+09:00",
        },
      ],
    } as DashboardView,
    insights,
  }));

  assert.match(html, /href="https:\/\/example\.com\/same-day-high"/);
  assert.match(html, /06\. 19\. AM 09:00/);
  assert.ok(html.indexOf("Same day higher impact") < html.indexOf("Latest low impact"));
  assert.ok(html.indexOf("Latest low impact") < html.indexOf("Older high impact"));
});
