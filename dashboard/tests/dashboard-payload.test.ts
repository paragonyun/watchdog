import assert from "node:assert/strict";
import test from "node:test";

import { validateDashboardPayload } from "../src/lib/dashboard-payload";

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
