import assert from "node:assert/strict";
import test from "node:test";

import { buildAssetSections } from "../src/lib/asset-groups";
import type { AssetSummary } from "../src/lib/dashboard-payload";

const assets: AssetSummary[] = [
  {
    symbol: "AAPL",
    name: "Apple",
    asset_type: "equity",
    value_krw: 20_000,
    weight_percent: 20,
    profit_loss_rate_percent: 3,
    price_source: "kis",
  },
  {
    symbol: "BTC",
    name: "Bitcoin",
    asset_type: "coin",
    value_krw: 10_000,
    weight_percent: 10,
    profit_loss_rate_percent: 8,
    price_source: "upbit",
  },
  {
    symbol: "CASH",
    name: "Cash",
    asset_type: "cash",
    value_krw: 5_000,
    weight_percent: 5,
    profit_loss_rate_percent: null,
    price_source: "manual",
  },
];

test("builds collapsed asset sections in the requested display order", () => {
  const sections = buildAssetSections(assets, { equity: 20_000, coin: 10_000, cash: 5_000 }, 35_000);

  assert.deepEqual(
    sections.map((section) => ({
      key: section.key,
      label: section.label,
      value: section.value_krw,
      weight: section.weight_percent,
      count: section.assets.length,
    })),
    [
      { key: "equity", label: "ISA", value: 20_000, weight: 57.14, count: 1 },
      { key: "coin", label: "코인", value: 10_000, weight: 28.57, count: 1 },
      { key: "cash", label: "현금", value: 5_000, weight: 14.29, count: 1 },
    ],
  );
});
