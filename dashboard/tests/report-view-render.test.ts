import assert from "node:assert/strict";
import test from "node:test";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ReportsScreen } from "../src/app/reports/page";
import type { ReportIndexItem, ResearchReportPayload } from "../src/lib/report-payload";

const report: ResearchReportPayload = {
  schema_version: "dashboard_report_v2",
  report_id: "portfolio-20260618-1607",
  generated_at: "2026-06-18T16:07:06+09:00",
  report_kind: "portfolio",
  title: "포트폴리오 전략 리포트",
  subtitle: "금리 재가격 구간에서 ISA 중심축 유지",
  document_status: "final",
  stance: "cautious",
  summary: {
    total_value_krw: 70_190_420,
    change_krw: -100_000,
    change_pct: -0.14,
    validation_valid: true,
  },
  executive_summary: [
    "핵심 ISA는 유지합니다.",
    "코인은 안정 신호 확인 전까지 관찰합니다.",
    "현금은 변동성 대응 여력으로 둡니다.",
  ],
  key_metrics: [
    { label: "총자산", value: "70,190,420원", context: "API 기준", tone: "neutral" },
    { label: "ISA 비중", value: "73.7%", context: "핵심 자산군", tone: "positive" },
    { label: "코인 비중", value: "16.3%", context: "관찰 필요", tone: "negative" },
  ],
  investment_thesis: {
    headline: "핵심 ISA는 유지하되 공격적 리밸런싱은 보류합니다.",
    body: "현재 포트폴리오는 ISA 중심의 장기 성장 노출이 명확하지만 금리와 코인 유동성 신호를 더 확인해야 합니다.",
    facts: ["KIS와 Upbit 모두 실제 API 값을 사용했습니다."],
    interpretations: ["금리 상승 구간에서는 성장주와 장기채가 동시에 흔들릴 수 있습니다."],
    estimates: ["금리 안정 전까지 코인 추가 매수는 보수적으로 봅니다."],
  },
  asset_views: [
    {
      symbol: "TIGER_SP500",
      name: "TIGER S&P500",
      action: "buy",
      thesis: "장기 핵심 자산으로 유지 가치가 높습니다.",
      catalysts: ["미국 대표지수 실적 안정"],
      risks: ["금리 재상승"],
    },
  ],
  scenarios: [
    { name: "상승", probability: "중간", trigger: "금리 안정", impact: "위험자산 반등", response: "분할 매수 검토" },
    { name: "기준", probability: "중간", trigger: "금리 횡보", impact: "제한적 등락", response: "기존 비중 유지" },
    { name: "하락", probability: "중간", trigger: "긴축 우려", impact: "동반 조정", response: "현금 유지" },
  ],
  risk_watchlist: ["미국 장기금리 재상승", "BTC 전저점 이탈"],
  conclusion: "현재 결론은 방어적 관찰입니다.",
  appendix: {
    asset_groups: { coin: 11_400_000, equity: 51_790_420, cash: 7_000_000 },
    assets: [
      {
        symbol: "TIGER_SP500",
        name: "TIGER S&P500",
        asset_type: "equity",
        value_krw: 12_000_000,
        weight_percent: 17.1,
        profit_loss_rate_percent: 8.2,
        price_source: "kis",
      },
    ],
    provider_status: [{ provider: "kis", used_fallback: false }],
    validation_issues: [],
  },
};

test("reports screen renders the institutional research document structure", () => {
  const index: ReportIndexItem[] = [{
    schema_version: report.schema_version,
    report_id: report.report_id,
    generated_at: report.generated_at,
    report_kind: report.report_kind,
    title: report.title,
    document_status: report.document_status,
    summary: report.summary,
  }];

  const html = renderToStaticMarkup(React.createElement(ReportsScreen, { index, report }));

  assert.match(html, /INSTITUTIONAL BRIEF/);
  assert.match(html, /리포트 핵심 판단/);
  assert.match(html, /자산 배분 스냅샷/);
  assert.match(html, /판단 변경 관찰 신호/);
  assert.match(html, /핵심 요약/);
});
