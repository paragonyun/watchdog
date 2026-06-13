import assert from "node:assert/strict";
import test from "node:test";

import { validateNewsRiskPayload } from "../src/lib/news-risk-payload";

const risk = {
  risk_id: "risk-1",
  scope: "direct",
  priority: "urgent",
  title: "비트코인 규제 위험",
  category: "규제",
  source_type: ["rss_rule", "codex_research"],
  facts: ["당국 발표"],
  potential_impact: "유동성 위축 가능성",
  transmission_path: "거래 제한 -> 유동성 축소",
  related_assets: ["BTC"],
  related_asset_groups: ["coin"],
  related_asset_weight_pct: 20,
  watch_indicators: ["거래량"],
  counter_evidence: ["시행 일정 미정"],
  priority_reasons: ["직접 관련 자산 (+2)"],
  source_links: [{ title: "공식 발표", url: "https://example.com/official" }],
  first_seen_at: "2026-06-13T08:00:00+00:00",
  last_updated_at: "2026-06-13T09:00:00+00:00",
  freshness: "new",
  change_reason: null,
};

const valid = {
  schema_version: "news_risk_payload_v1",
  generated_at: "2026-06-13T09:00:00+00:00",
  lookback_hours: 72,
  rss_generated_at: "2026-06-13T09:00:00+00:00",
  codex_generated_at: null,
  status: "actual",
  direct_risks: [risk],
  market_risks: [],
};

test("accepts privacy-safe news risk payload", () => {
  assert.equal(validateNewsRiskPayload(valid), true);
});

test("rejects malformed scope, sensitive fields, and unsafe links", () => {
  assert.equal(validateNewsRiskPayload({ ...valid, status: "unknown" }), false);
  assert.equal(validateNewsRiskPayload({ ...valid, generated_at: "2026" }), false);
  assert.equal(validateNewsRiskPayload({ ...valid, direct_risks: [{ ...risk, scope: "market" }] }), false);
  assert.equal(validateNewsRiskPayload({ ...valid, direct_risks: [{ ...risk, quantity: 1 }] }), false);
  assert.equal(
    validateNewsRiskPayload({
      ...valid,
      direct_risks: [{ ...risk, source_links: [{ title: "internal", url: "http://127.0.0.1/private" }] }],
    }),
    false,
  );
  assert.equal(
    validateNewsRiskPayload({
      ...valid,
      direct_risks: [{ ...risk, source_links: [{ title: "ipv6-loopback", url: "http://[::1]/private" }] }],
    }),
    false,
  );
});
