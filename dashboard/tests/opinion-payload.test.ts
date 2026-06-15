import assert from "node:assert/strict";
import test from "node:test";

import { validateOpinionPayload } from "../src/lib/opinion-payload";

const payload = {
  schema_version: "dashboard_opinion_v1",
  opinion_id: "opinion-20260615-1200",
  generated_at: "2026-06-15T12:00:00+09:00",
  portfolio_posture: "observe",
  summary: "변동성 확인이 우선입니다.",
  items: [{
    id: "btc-observe",
    symbol: "BTC",
    name: "비트코인",
    action: "observe",
    confidence: "medium",
    thesis: "유동성 회복 여부를 확인합니다.",
    evidence: ["비중이 목표 범위 상단입니다."],
    counter_evidence: ["ETF 자금 유입은 우호적입니다."],
    catalysts: ["거래대금 회복"],
    invalidation_conditions: ["ETF 순유출 확대"],
    suggested_position_note: "신규 매수는 회복 확인 후 검토",
    sources: [{ label: "Codex 분석", url: null }],
  }],
  disclaimer: "Codex 판단이며 투자 자문이나 자동 주문이 아닙니다.",
};

test("accepts Codex-authored buy/sell/observe payload", () => {
  assert.equal(validateOpinionPayload(payload), true);
  assert.equal(validateOpinionPayload({ ...payload, items: [{ ...payload.items[0], action: "buy" }] }), true);
  assert.equal(validateOpinionPayload({ ...payload, items: [{ ...payload.items[0], action: "sell" }] }), true);
});

test("rejects legacy rule actions and sensitive fields", () => {
  assert.equal(validateOpinionPayload({ ...payload, items: [{ ...payload.items[0], action: "review" }] }), false);
  assert.equal(validateOpinionPayload({ ...payload, items: [{ ...payload.items[0], quantity: 1 }] }), false);
});
