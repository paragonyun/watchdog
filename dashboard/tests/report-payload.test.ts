import assert from "node:assert/strict";
import test from "node:test";

import { validateReportPayload } from "../src/lib/report-payload";

const report = {
  schema_version: "dashboard_report_v1",
  report_id: "portfolio-20260613-0900",
  generated_at: "2026-06-13T09:00:00",
  report_kind: "portfolio",
  title: "포트폴리오 리포트",
  document_status: "final",
  summary: {
    total_value_krw: 1_000,
    change_krw: 50,
    change_pct: 5,
    validation_valid: true,
  },
  sections: [
    { title: "핵심 판단", lines: ["현 상태를 재검토합니다."] },
  ],
  appendix: {
    asset_groups: { coin: 200, equity: 700, cash: 100 },
    assets: [
      {
        symbol: "BTC",
        name: "비트코인",
        asset_type: "coin",
        value_krw: 200,
        weight_percent: 20,
        profit_loss_rate_percent: 10,
        price_source: "upbit",
      },
    ],
    provider_status: [{ provider: "upbit", used_fallback: false }],
    validation_issues: [],
  },
};

test("accepts privacy-safe report archive payload", () => {
  assert.equal(validateReportPayload(report), true);
});

test("rejects unsafe report ids and sensitive nested fields", () => {
  assert.equal(validateReportPayload({ ...report, report_id: "../private" }), false);
  assert.equal(
    validateReportPayload({
      ...report,
      appendix: {
        ...report.appendix,
        assets: [{ ...report.appendix.assets[0], quantity: 0.01 }],
      },
    }),
    false,
  );
});
