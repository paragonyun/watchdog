import assert from "node:assert/strict";
import test from "node:test";

import { validateDashboardPayload, validateDashboardPayloadV2 } from "../src/lib/dashboard-payload";

test("dashboard payload validator accepts summary payload", () => {
  assert.equal(
    validateDashboardPayload({
      schema_version: "dashboard_payload_v1",
      generated_at: "2026-06-05T08:00:00",
      report_kind: "portfolio",
      total_value_krw: 1000,
      asset_groups: { coin: 200, equity: 700, cash: 100 },
      assets: [],
      trend: { change_krw: 0, change_pct: null },
      news_impacts: [],
      provider_status: [],
    }),
    true,
  );
});

test("dashboard payload validator rejects raw report payloads", () => {
  assert.equal(
    validateDashboardPayload({
      schema_version: 1,
      current_portfolio: { total_value_krw: 1000 },
    }),
    false,
  );
});

test("dashboard v2 validator accepts privacy-safe performance payload", () => {
  assert.equal(
    validateDashboardPayloadV2({
      schema_version: "dashboard_payload_v2",
      generated_at: "2026-06-12T19:28:50+09:00",
      total_value_krw: 1000,
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
        max_drawdown_pct: -3.1,
        status: "confirmed",
      },
      asset_groups: [],
      assets: [],
      provider_status: [],
    }),
    true,
  );
});

test("dashboard validator rejects malformed v2 performance payload", () => {
  assert.equal(
    validateDashboardPayload({
      schema_version: "dashboard_payload_v2",
      total_value_krw: 1000,
      performance: { cumulative_twr_pct: "8.4" },
      asset_groups: [],
      assets: [],
      provider_status: [],
    }),
    false,
  );
});

test("dashboard validator rejects sensitive or malformed nested v2 fields", () => {
  const base = {
    schema_version: "dashboard_payload_v2",
    generated_at: "2026-06-12T19:28:50+09:00",
    total_value_krw: 1000,
    data_freshness: {},
    performance: {},
    asset_groups: [],
    provider_status: [],
  };

  assert.equal(validateDashboardPayload({ ...base, assets: [{ quantity: 0.01 }] }), false);
  assert.equal(validateDashboardPayload({ ...base, assets: ["BTC"] }), false);
  assert.equal(validateDashboardPayload({ ...base, asset_groups: [null], assets: [] }), false);
});
