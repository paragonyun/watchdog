import Link from "next/link";

import {
  Brand,
  DesktopSideNavigation,
  DesktopTopNavigation,
  MobileBottomNavigation,
  MobileHeader,
} from "@/components/app-navigation";
import { requireSession } from "@/lib/auth";
import { formatDashboardDate } from "@/lib/format-date";
import {
  buildReportQualityView,
  isResearchReport,
  type ReportIndexItem,
  type ReportPayload,
  type ReportQualityView,
  type ResearchReportPayload,
} from "@/lib/report-payload";
import { getReportIndex, getReportPayload } from "@/lib/storage";

export const dynamic = "force-dynamic";

export default async function ReportsPage({ searchParams }: { searchParams: Promise<{ id?: string }> }) {
  await requireSession();
  const index = await getReportIndex();
  const requestedId = (await searchParams).id;
  const selectedId = index.some((item) => item.report_id === requestedId)
    ? requestedId
    : index.find((item) => item.schema_version === "dashboard_report_v2")?.report_id ?? index[0]?.report_id;
  const report = selectedId ? await getReportPayload(selectedId) : null;

  if (!index.length || !report) return <EmptyReportsPage />;
  return <ReportsScreen index={index} report={report} />;
}

export function ReportsScreen({ index, report }: { index: ReportIndexItem[]; report: ReportPayload }) {
  const completedCount = index.filter((item) => item.schema_version === "dashboard_report_v2").length;
  const quality = buildReportQualityView(report);
  return (
    <div className="app-frame">
      <DesktopTopNavigation active="reports" />
      <DesktopSideNavigation active="reports" />
      <main className="dashboard-main reports-main">
        <MobileHeader />
        <header className="reports-title">
          <div>
            <span>CODEX RESEARCH</span>
            <h1>리서치 리포트</h1>
            <p>숫자 나열이 아닌 투자 논리, 촉매, 시나리오와 위험을 담은 완성 리포트입니다.</p>
          </div>
          <div className={`reports-status ${isResearchReport(report) ? "valid" : "review"}`}>
            <span>선택 문서</span>
            <strong>{isResearchReport(report) ? "완성 리포트" : "작성 원본"}</strong>
            <small>{formatDashboardDate(report.generated_at)} 기준</small>
          </div>
        </header>

        <section className="reports-summary">
          <ReportSummary label="보관 문서" value={`${index.length}건`} detail="최근 50건 유지" tone="archive" />
          <ReportSummary label="완성 리포트" value={`${completedCount}건`} detail="Codex 최종 분석" tone="final" />
          <ReportSummary label="QC 상태" value={quality.status === "pass" ? "통과" : "보강 필요"} detail="본문, 근거, 부록 검증" tone="valid" />
          <ReportSummary label="현재 문서" value={kindLabel(report.report_kind)} detail={statusLabel(report)} tone="current" />
        </section>

        <section className="reports-layout">
          <ReportIndex index={index} selected={report.report_id} />
          <div className="reports-document-stack">
            {isResearchReport(report) ? <ResearchDocument report={report} /> : <LegacyDocument report={report} />}
            <ReportQualityPanel quality={quality} />
          </div>
        </section>

        <footer className="reports-footnote">
          <span>사실, 해석, 추정을 분리하고 반대 논리와 위험 요인을 함께 제시합니다.</span>
          <span>본 리포트는 개인 의사결정 보조 자료이며 투자 자문이나 자동 주문이 아닙니다.</span>
        </footer>
      </main>
      <MobileBottomNavigation active="reports" />
    </div>
  );
}

function ReportIndex({ index, selected }: { index: ReportIndexItem[]; selected: string }) {
  return (
    <aside className="surface reports-index">
      <header><h2>리포트 목록</h2><span>{index.length}건</span></header>
      <nav aria-label="리포트 목록">
        {index.map((item) => (
          <Link className={item.report_id === selected ? "active" : ""} href={`/reports?id=${encodeURIComponent(item.report_id)}`} key={item.report_id}>
            <div>
              <span>{kindLabel(item.report_kind)}</span>
              <b className={item.schema_version === "dashboard_report_v2" ? "valid" : "review"}>
                {item.schema_version === "dashboard_report_v2" ? "완성 리포트" : "작성 원본"}
              </b>
            </div>
            <strong>{item.title}</strong>
            <small>{formatDashboardDate(item.generated_at)} · {statusLabel(item)}</small>
            <em>{formatSignedKrw(item.summary.change_krw)} · {formatPercent(item.summary.change_pct)}</em>
          </Link>
        ))}
      </nav>
    </aside>
  );
}

function ResearchDocument({ report }: { report: ResearchReportPayload }) {
  const fallbackCount = report.appendix.provider_status.filter((provider) => provider.used_fallback).length;
  const dataStatus = fallbackCount ? `${fallbackCount}개 출처 대체값` : "Live 데이터";
  return (
    <article className="surface report-document research-document">
      <header className={`research-masthead ${report.stance}`}>
        <div>
          <span>{kindLabel(report.report_kind)} · INSTITUTIONAL BRIEF</span>
          <h2>{report.title}</h2>
          <p>{report.subtitle}</p>
        </div>
        <div className="research-stance">
          <small>INVESTMENT VIEW</small>
          <strong>{stanceLabel(report.stance)}</strong>
          <span>{stanceDescription(report.stance)}</span>
        </div>
      </header>

      <section className="research-decision-band" aria-label="리포트 핵심 판단">
        <article>
          <span>총자산</span>
          <strong>{formatKrw(report.summary.total_value_krw)}</strong>
          <small>{formatDashboardDate(report.generated_at)} 기준</small>
        </article>
        <article>
          <span>기간 변화</span>
          <strong className={tone(report.summary.change_krw)}>{formatSignedKrw(report.summary.change_krw)}</strong>
          <small>{formatPercent(report.summary.change_pct)}</small>
        </article>
        <article>
          <span>데이터 상태</span>
          <strong>{dataStatus}</strong>
          <small>{report.summary.validation_valid ? "숫자 검증 통과" : "숫자 재검토 필요"}</small>
        </article>
        <article>
          <span>문서 결론</span>
          <strong>{stanceLabel(report.stance)}</strong>
          <small>{report.risk_watchlist.length}개 관찰 신호</small>
        </article>
      </section>

      <section className="research-metrics">
        {report.key_metrics.map((metric) => (
          <article className={metric.tone} key={metric.label}>
            <span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.context}</small>
          </article>
        ))}
      </section>

      <section className="research-executive">
        <div>
          <span>EXECUTIVE SUMMARY</span>
          <h3>{report.investment_thesis.headline}</h3>
          <p>리포트 전체 결론을 먼저 제시하고, 세부 근거는 아래 본문과 부록에서 검증합니다.</p>
        </div>
        <ol>{report.executive_summary.map((item) => <li key={item}>{item}</li>)}</ol>
      </section>

      <section className="research-body">
        <article className="research-thesis">
          <ResearchSectionHeader number="01" title="투자 논리" caption="결론을 뒷받침하는 핵심 가설과 근거 레이어" />
          <p>{report.investment_thesis.body}</p>
          <div className="research-evidence-grid">
            <Evidence label="사실" items={report.investment_thesis.facts} />
            <Evidence label="해석" items={report.investment_thesis.interpretations} />
            <Evidence label="추정" items={report.investment_thesis.estimates} />
          </div>
        </article>

        <article>
          <ResearchSectionHeader number="02" title="자산 배분 스냅샷" caption="현재 비중과 자산군 집중도를 리포트 본문 안에서 재확인" />
          <AllocationSnapshot report={report} />
        </article>

        <article>
          <ResearchSectionHeader number="03" title="자산별 전략" caption="매수, 매도, 관찰 필요를 단순 구분하고 조건부 변화 요인을 표시" />
          <div className="research-asset-views">
            {report.asset_views.map((view) => (
              <section key={view.symbol}>
                <div>
                  <span className={view.action}>{actionLabel(view.action)}</span>
                  <h4>{view.name}</h4>
                  <small>{view.symbol} · {actionDescription(view.action)}</small>
                </div>
                <p>{view.thesis}</p>
                <Evidence label="촉매" items={view.catalysts} />
                <Evidence label="위험" items={view.risks} />
              </section>
            ))}
          </div>
        </article>

        <article>
          <ResearchSectionHeader number="04" title="시나리오 분석" caption="상승, 기준, 하락 경로별로 판단이 바뀌는 조건과 대응을 분리" />
          <div className="scenario-table">
            {report.scenarios.map((scenario) => (
              <section key={scenario.name}>
                <div><strong>{scenario.name}</strong><span>{scenario.probability}</span></div>
                <p><b>조건</b>{scenario.trigger}</p><p><b>영향</b>{scenario.impact}</p><p><b>대응</b>{scenario.response}</p>
              </section>
            ))}
          </div>
        </article>

        <article className="research-conclusion">
          <ResearchSectionHeader number="05" title="결론 및 위험 점검" caption="다음 행동 원칙과 판단 변경 신호" />
          <div className="research-conclusion-grid">
            <blockquote>{report.conclusion}</blockquote>
            <section>
              <h4>판단 변경 관찰 신호</h4>
              <ul>{report.risk_watchlist.map((risk) => <li key={risk}>{risk}</li>)}</ul>
            </section>
          </div>
        </article>
      </section>
      <ReportAppendix report={report} />
    </article>
  );
}

function ResearchSectionHeader({ number, title, caption }: { number: string; title: string; caption: string }) {
  return (
    <header className="research-section-heading">
      <span>{number}</span>
      <div>
        <h3>{title}</h3>
        <p>{caption}</p>
      </div>
    </header>
  );
}

function AllocationSnapshot({ report }: { report: ResearchReportPayload }) {
  const total = report.summary.total_value_krw;
  const groups = [
    { key: "equity", label: "ISA", value: report.appendix.asset_groups.equity, className: "isa" },
    { key: "coin", label: "코인", value: report.appendix.asset_groups.coin, className: "coin" },
    { key: "cash", label: "현금", value: report.appendix.asset_groups.cash, className: "cash" },
  ];

  return (
    <div className="research-allocation-snapshot">
      {groups.map((group) => {
        const weight = total > 0 ? group.value / total * 100 : 0;
        return (
          <section key={group.key}>
            <div>
              <strong>{group.label}</strong>
              <span>{formatKrw(group.value)}</span>
              <b>{formatPercent(weight, false)}</b>
            </div>
            <i className={group.className} style={{ width: `${Math.min(100, Math.max(0, weight))}%` }} />
          </section>
        );
      })}
    </div>
  );
}

function LegacyDocument({ report }: { report: Exclude<ReportPayload, ResearchReportPayload> }) {
  return (
    <article className="surface report-document legacy-document">
      <header className="report-document-header">
        <div><span>작성 원본 · 참고 자료</span><h2>{report.title}</h2><p>{formatDashboardDate(report.generated_at)} 생성</p></div>
        <div><strong>{formatKrw(report.summary.total_value_krw)}</strong><span className={tone(report.summary.change_krw)}>{formatSignedKrw(report.summary.change_krw)}</span></div>
      </header>
      <div className="legacy-notice">이 문서는 완성 리서치 리포트가 아닌 작성 원본입니다. 최신 완성 리포트가 등록되면 기본 화면에서 우선 표시됩니다.</div>
      <div className="report-sections">
        {report.sections.map((section, index) => <section key={`${section.title}-${index}`}><h3>{section.title}</h3><ul>{section.lines.map((line) => <li key={line}>{line}</li>)}</ul></section>)}
      </div>
      <ReportAppendix report={report} />
    </article>
  );
}

function Evidence({ label, items }: { label: string; items: string[] }) {
  return <section className="research-evidence"><h4>{label}</h4><ul>{items.map((item) => <li key={item}>{item}</li>)}</ul></section>;
}

function ReportAppendix({ report }: { report: ReportPayload }) {
  return (
    <details className="report-appendix">
      <summary>상세 부록 보기</summary>
      <div className="report-appendix-body">
        <section><h3>자산별 스냅샷</h3><div className="report-asset-table">{report.appendix.assets.map((asset) => <article key={asset.symbol}><div><strong>{asset.name}</strong><span>{asset.symbol}</span></div><div><small>평가액</small><b>{formatKrw(asset.value_krw)}</b></div><div><small>비중</small><b>{formatPercent(asset.weight_percent, false)}</b></div><div><small>누계 수익률</small><b className={tone(asset.profit_loss_rate_percent)}>{formatPercent(asset.profit_loss_rate_percent)}</b></div></article>)}</div></section>
        <section className="report-qc-grid"><div><h3>제공자 상태</h3>{report.appendix.provider_status.map((provider) => <p key={provider.provider}><span className={provider.used_fallback ? "review" : "valid"} />{provider.provider} · {provider.used_fallback ? "대체값 사용" : "정상"}</p>)}</div><div><h3>검증 결과</h3>{report.appendix.validation_issues.length ? report.appendix.validation_issues.map((issue) => <p key={issue}>{issue}</p>) : <p>숫자·비중·변화율 기본 검증 통과</p>}</div></section>
      </div>
    </details>
  );
}

function ReportQualityPanel({ quality }: { quality: ReportQualityView }) {
  return (
    <section className={`surface report-quality-panel ${quality.status}`}>
      <header>
        <div>
          <span>REPORT QC</span>
          <h2>리포트 품질 점검</h2>
        </div>
        <strong>{quality.status === "pass" ? "통과" : "보강 필요"}</strong>
      </header>
      <p>{quality.summary}</p>
      <div className="report-quality-grid">
        {quality.checks.map((check) => (
          <article className={check.status} key={check.id}>
            <span>{check.status === "pass" ? "PASS" : "REVIEW"}</span>
            <h3>{check.label}</h3>
            <p>{check.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function ReportSummary({ label, value, detail, tone: itemTone }: { label: string; value: string; detail: string; tone: "archive" | "final" | "valid" | "current" }) {
  return <article className={`reports-summary-item ${itemTone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function EmptyReportsPage() {
  return <main className="empty-dashboard-page"><Brand /><section className="surface"><h1>업로드된 리포트가 없습니다</h1><p>Codex가 작성한 완성 리포트 JSON을 `sync-report --path &lt;파일&gt;`로 동기화하면 표시됩니다.</p></section></main>;
}

function kindLabel(value: "portfolio" | "weekly"): string { return value === "weekly" ? "주간 리포트" : "포트폴리오 리포트"; }
function statusLabel(value: Pick<ReportIndexItem, "document_status" | "schema_version">): string { return value.schema_version === "dashboard_report_v2" ? "완성 리포트" : value.document_status === "final" ? "기존 최종본" : "작성 원본"; }
function stanceLabel(value: ResearchReportPayload["stance"]): string { return value === "positive" ? "긍정적" : value === "cautious" ? "신중" : "중립"; }
function stanceDescription(value: ResearchReportPayload["stance"]): string { return value === "positive" ? "위험 대비 기대수익 우위" : value === "cautious" ? "방어와 확인 우선" : "기존 비중 유지"; }
function actionLabel(value: ResearchReportPayload["asset_views"][number]["action"]): string { return value === "buy" ? "매수" : value === "sell" ? "매도" : "관찰 필요"; }
function actionDescription(value: ResearchReportPayload["asset_views"][number]["action"]): string { return value === "buy" ? "분할 접근 후보" : value === "sell" ? "축소 또는 회피 후보" : "조건 확인 전 보류"; }
function formatKrw(value: number): string { return `${Math.round(value).toLocaleString("ko-KR")}원`; }
function formatSignedKrw(value: number): string { return `${value > 0 ? "+" : ""}${formatKrw(value)}`; }
function formatPercent(value: number | null, signed = true): string { return value === null ? "-" : `${signed && value > 0 ? "+" : ""}${value.toFixed(2)}%`; }
function tone(value: number | null): string { return value === null || value === 0 ? "neutral-text" : value > 0 ? "positive-text" : "negative-text"; }
