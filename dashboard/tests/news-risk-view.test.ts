import assert from "node:assert/strict";
import test from "node:test";

import { buildNewsRiskView } from "../src/lib/news-risk-view";
import type { NewsRiskItem, NewsRiskPayload } from "../src/lib/news-risk-payload";

function risk(overrides: Partial<NewsRiskItem>): NewsRiskItem {
  return {
    risk_id: "risk-1",
    scope: "direct",
    priority: "watch",
    title: "시장 변동성 확대",
    category: "유동성",
    source_type: ["rss_rule"],
    facts: ["시장 변동성이 확대되었습니다."],
    potential_impact: "관련 자산 가격 변동성이 커질 수 있습니다.",
    transmission_path: "유동성 축소 -> 가격 변동성 확대",
    related_assets: ["BTC"],
    related_asset_groups: ["coin"],
    related_asset_weight_pct: 10,
    watch_indicators: ["거래량"],
    counter_evidence: ["자금 유입 회복"],
    priority_reasons: ["관련 자산 비중"],
    source_links: [{ title: "기사", url: "https://example.com/news" }],
    first_seen_at: "2026-06-13T00:00:00+00:00",
    last_updated_at: "2026-06-13T01:00:00+00:00",
    freshness: "active",
    change_reason: null,
    ...overrides,
  };
}

const payload: NewsRiskPayload = {
  schema_version: "news_risk_payload_v1",
  generated_at: "2026-06-13T09:00:00+00:00",
  lookback_hours: 72,
  rss_generated_at: "2026-06-13T09:00:00+00:00",
  codex_generated_at: "2026-06-13T08:00:00+00:00",
  status: "actual",
  direct_risks: [
    risk({ risk_id: "watch-new", freshness: "new", related_asset_weight_pct: 30 }),
    risk({ risk_id: "urgent-active", priority: "urgent", related_asset_weight_pct: 10 }),
    risk({ risk_id: "urgent-new", priority: "urgent", freshness: "new", source_type: ["rss_rule", "codex_research"] }),
  ],
  market_risks: [
    risk({
      risk_id: "market-refresh",
      scope: "market",
      priority: "caution",
      freshness: "refresh_required",
      related_assets: [],
      related_asset_groups: ["isa", "coin"],
    }),
  ],
};

test("sorts risks by priority, freshness, and related asset weight", () => {
  const view = buildNewsRiskView(payload);

  assert.deepEqual(view.directRisks.map((item) => item.id), ["urgent-new", "urgent-active", "watch-new"]);
  assert.equal(view.directRisks[0].priorityLabel, "긴급");
  assert.equal(view.directRisks[0].freshnessLabel, "신규");
  assert.deepEqual(view.directRisks[0].sourceLabels, ["RSS 규칙", "Codex 심층 분석"]);
});

test("summarizes scope counts, freshness, and refresh state", () => {
  const view = buildNewsRiskView(payload);

  assert.equal(view.directCount, 3);
  assert.equal(view.marketCount, 1);
  assert.equal(view.newCount, 2);
  assert.equal(view.needsRefresh, true);
  assert.equal(view.statusLabel, "최신");
  assert.equal(view.codexGeneratedAt, "2026-06-13T08:00:00+00:00");
});

