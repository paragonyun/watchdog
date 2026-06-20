import assert from "node:assert/strict";
import test from "node:test";

import { buildReportQualityView, validateReportPayload } from "../src/lib/report-payload";

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

test("accepts completed analyst-style v2 reports and rejects source documents", () => {
  const v2 = {
    ...report,
    schema_version: "dashboard_report_v2",
    subtitle: "변동성 확대 구간의 선택과 집중",
    stance: "cautious",
    executive_summary: ["핵심 자산은 유지하고 신규 위험 노출은 선별합니다."],
    key_metrics: [{ label: "누적 TWR", value: "+8.4%", context: "벤치마크 대비 +4.2%p", tone: "positive" }],
    investment_thesis: {
      headline: "수익 기여와 위험 집중도를 함께 관리합니다.",
      body: "현재 데이터와 주요 촉매를 바탕으로 판단했습니다.",
      facts: ["ISA가 자산의 중심입니다."],
      interpretations: ["시장 조정 시 변동성이 확대될 수 있습니다."],
      estimates: ["현금이 완충 역할을 할 전망입니다."],
    },
    asset_views: [{
      symbol: "BTC",
      name: "비트코인",
      action: "observe",
      thesis: "유동성 확인이 우선입니다.",
      catalysts: ["ETF 순유입 회복"],
      risks: ["거래대금 감소"],
    }],
    scenarios: [{ name: "기준", probability: "중간", trigger: "금리 안정", impact: "완만한 회복", response: "현 비중 유지" }],
    risk_watchlist: ["코인 변동성 확대"],
    conclusion: "현금 완충력을 보존합니다.",
  };

  assert.equal(validateReportPayload(v2), true);
  assert.equal(validateReportPayload({ ...v2, document_status: "source" }), false);
});

test("builds report quality checks beyond JSON validity", () => {
  const v2 = {
    ...report,
    schema_version: "dashboard_report_v2",
    subtitle: "변동성 관리가 필요한 구간",
    stance: "cautious",
    executive_summary: ["요약입니다."],
    key_metrics: [{ label: "총자산", value: "1,000원", context: "검증용", tone: "neutral" }],
    investment_thesis: {
      headline: "핵심 논리",
      body: "본문입니다.",
      facts: ["사실"],
      interpretations: ["해석"],
      estimates: ["추정"],
    },
    asset_views: [{
      symbol: "BTC",
      name: "비트코인",
      action: "observe",
      thesis: "관찰 필요",
      catalysts: ["촉매"],
      risks: ["위험"],
    }],
    scenarios: [{ name: "기준", probability: "중간", trigger: "금리 안정", impact: "회복", response: "유지" }],
    risk_watchlist: ["변동성"],
    conclusion: "결론입니다.",
  };

  const quality = buildReportQualityView(v2);

  assert.equal(quality.status, "review");
  assert.equal(quality.checks.find((check) => check.id === "executive")?.status, "review");
  assert.equal(quality.checks.find((check) => check.id === "evidence")?.status, "pass");
  assert.equal(quality.checks.find((check) => check.id === "scenarios")?.status, "review");
});
