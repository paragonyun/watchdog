import assert from "node:assert/strict";
import test from "node:test";

import { buildRiskView } from "../src/lib/risk-view";
import type { DashboardView } from "../src/lib/dashboard-view";

const baseView = {
  status: "actual",
  performance: { cumulativeTwrPct: null, monthTwrPct: null, benchmarkReturnPct: null, excessReturnPct: null, maxDrawdownPct: -4, status: "confirmed" },
  groups: [
    { key: "isa", label: "ISA", valueKrw: 60, weightPercent: 60, targetWeightPercent: 50, targetDiffPercentagePoints: 10 },
    { key: "coin", label: "코인", valueKrw: 30, weightPercent: 30, targetWeightPercent: 25, targetDiffPercentagePoints: 5 },
    { key: "cash", label: "현금 및 예수금", valueKrw: 10, weightPercent: 10, targetWeightPercent: 10, targetDiffPercentagePoints: 0 },
  ],
  assets: [
    { symbol: "A", name: "A", assetType: "isa", valueKrw: 30, weightPercent: 30, profitLossRatePercent: -25, targetDiffPercentagePoints: null, priceSource: "kis" },
    { symbol: "B", name: "B", assetType: "isa", valueKrw: 20, weightPercent: 20, profitLossRatePercent: -5, targetDiffPercentagePoints: null, priceSource: "kis" },
    { symbol: "C", name: "C", assetType: "coin", valueKrw: 15, weightPercent: 15, profitLossRatePercent: -30, targetDiffPercentagePoints: null, priceSource: "upbit" },
  ],
  providers: [
    { provider: "kis", status: "actual", usedFallback: false },
    { provider: "upbit", status: "actual", usedFallback: false },
  ],
} as DashboardView;

test("builds explainable risk checks from current portfolio data", () => {
  const risk = buildRiskView(baseView);

  assert.equal(risk.largestAsset?.symbol, "A");
  assert.equal(risk.topThreeWeightPercent, 65);
  assert.equal(risk.lossExposureWeightPercent, 45);
  assert.equal(risk.maxGroupDeviationPercentagePoints, 10);
  assert.equal(risk.highCount, 4);
  assert.equal(risk.mediumCount, 0);
  assert.equal(risk.highestLevel, "high");
});

test("flags fallback and insufficient performance history without inventing drawdown", () => {
  const risk = buildRiskView({
    ...baseView,
    status: "fallback",
    performance: { ...baseView.performance, maxDrawdownPct: null, status: "insufficient_data" },
    providers: [{ provider: "upbit", status: "fallback", usedFallback: true }],
  });

  assert.equal(risk.checks.find((item) => item.id === "data")?.level, "high");
  assert.equal(risk.checks.find((item) => item.id === "history")?.level, "medium");
  assert.equal(risk.maxDrawdownPct, null);
});
