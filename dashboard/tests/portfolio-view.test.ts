import assert from "node:assert/strict";
import test from "node:test";

import { buildPortfolioSections } from "../src/lib/portfolio-view";
import type { DashboardView } from "../src/lib/dashboard-view";

const view = {
  totalValueKrw: 100,
  groups: [
    { key: "isa", label: "ISA", valueKrw: 70, weightPercent: 70, targetWeightPercent: 60, targetDiffPercentagePoints: 10 },
    { key: "coin", label: "코인", valueKrw: 20, weightPercent: 20, targetWeightPercent: 25, targetDiffPercentagePoints: -5 },
    { key: "cash", label: "현금 및 예수금", valueKrw: 10, weightPercent: 10, targetWeightPercent: 15, targetDiffPercentagePoints: -5 },
  ],
  assets: [
    { symbol: "ETF", name: "ETF", assetType: "isa", valueKrw: 70, weightPercent: 70, profitLossRatePercent: 12, targetDiffPercentagePoints: 2, priceSource: "kis" },
    { symbol: "BTC", name: "Bitcoin", assetType: "coin", valueKrw: 20, weightPercent: 20, profitLossRatePercent: -8, targetDiffPercentagePoints: -1, priceSource: "upbit" },
    { symbol: "CASH", name: "Cash", assetType: "cash", valueKrw: 10, weightPercent: 10, profitLossRatePercent: null, targetDiffPercentagePoints: null, priceSource: null },
  ],
} as DashboardView;

test("builds portfolio sections in ISA, coin, cash order", () => {
  const sections = buildPortfolioSections(view);

  assert.deepEqual(
    sections.map((section) => ({
      key: section.key,
      count: section.assets.length,
      value: section.valueKrw,
      targetDiff: section.targetDiffPercentagePoints,
    })),
    [
      { key: "isa", count: 1, value: 70, targetDiff: 10 },
      { key: "coin", count: 1, value: 20, targetDiff: -5 },
      { key: "cash", count: 1, value: 10, targetDiff: -5 },
    ],
  );
});

test("sorts assets by value within each portfolio section", () => {
  const extended = {
    ...view,
    assets: [
      ...view.assets,
      { symbol: "SMALL", name: "Small", assetType: "isa", valueKrw: 5, weightPercent: 5, profitLossRatePercent: 1, targetDiffPercentagePoints: null, priceSource: "kis" },
    ],
  };

  assert.deepEqual(buildPortfolioSections(extended).find((section) => section.key === "isa")?.assets.map((asset) => asset.symbol), ["ETF", "SMALL"]);
});
