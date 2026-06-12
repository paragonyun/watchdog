import assert from "node:assert/strict";
import test from "node:test";

import { buildDashboardView } from "../src/lib/dashboard-view";
import type { DashboardPayload, DashboardPayloadV2 } from "../src/lib/dashboard-payload";

const v1: DashboardPayload = {
  schema_version: "dashboard_payload_v1",
  generated_at: "2026-06-12T19:20:00+09:00",
  report_kind: "portfolio",
  total_value_krw: 1000,
  asset_groups: { equity: 700, coin: 200, cash: 100 },
  assets: [
    {
      symbol: "BTC",
      name: "비트코인",
      asset_type: "coin",
      value_krw: 200,
      weight_percent: 20,
      profit_loss_rate_percent: 12,
      price_source: "upbit",
    },
  ],
  trend: {
    start_total_krw: 900,
    latest_total_krw: 1000,
    change_krw: 100,
    change_pct: 11.11,
    snapshot_count: 3,
  },
  news_impacts: [
    {
      title: "ETF 자금 유입",
      impact: "긍정",
      impact_score: 2,
      score_label: "규칙 기반",
      related_assets: ["BTC"],
      reason: "비트코인 관련",
      why_it_matters: "보유 자산 관련",
    },
  ],
  provider_status: [{ provider: "upbit", used_fallback: false }],
};

const v2: DashboardPayloadV2 = {
  schema_version: "dashboard_payload_v2",
  generated_at: "2026-06-12T19:28:50+09:00",
  total_value_krw: 1100,
  data_freshness: {
    portfolio_status: "actual",
    last_actual_at: "2026-06-12T19:28:50+09:00",
    reconciliation_status: "reconciled",
  },
  performance: {
    cumulative_twr_pct: 8.4,
    month_twr_pct: 2.1,
    benchmark_return_pct: 4.2,
    excess_return_pct: 4.2,
    max_drawdown_pct: -3,
    status: "confirmed",
  },
  asset_groups: [
    { asset_group: "isa", value_krw: 800, weight_percent: 72.73, target_diff_percentage_points: 2.73 },
    { asset_group: "coin", value_krw: 200, weight_percent: 18.18, target_diff_percentage_points: -1.82 },
    { asset_group: "cash", value_krw: 100, weight_percent: 9.09, target_diff_percentage_points: -0.91 },
  ],
  assets: [],
  provider_status: [{ provider: "upbit", status: "actual", used_fallback: false }],
};

test("dashboard view merges v1 context with v2 performance", () => {
  const view = buildDashboardView(v1, v2);

  assert.equal(view.totalValueKrw, 1100);
  assert.equal(view.generatedAt, v2.generated_at);
  assert.equal(view.performance.cumulativeTwrPct, 8.4);
  assert.equal(view.performance.benchmarkReturnPct, 4.2);
  assert.equal(view.periodChange.changeKrw, 100);
  assert.equal(view.news.length, 1);
  assert.equal(view.groups[0].label, "ISA");
  assert.equal(view.groups[0].targetWeightPercent, 70);
  assert.equal(view.assets[0].priceSource, "upbit");
});

test("dashboard view derives attention only from actual status data", () => {
  const view = buildDashboardView(v1, {
    ...v2,
    data_freshness: {
      portfolio_status: "stale",
      reconciliation_status: "reconciliation_required",
    },
    performance: { ...v2.performance, status: "provisional" },
  });

  assert.deepEqual(
    view.attention.map((item) => item.title),
    ["데이터 최신성 확인 필요", "보유수량 대사 필요", "성과 수치 잠정 상태"],
  );
  assert.deepEqual(view.opinions, []);
  assert.deepEqual(view.calendar, []);
  assert.deepEqual(view.reports, []);
});
