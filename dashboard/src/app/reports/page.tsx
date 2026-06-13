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
import type { ReportIndexItem, ReportPayload } from "@/lib/report-payload";
import { getReportIndex, getReportPayload } from "@/lib/storage";

export const dynamic = "force-dynamic";

export default async function ReportsPage({
  searchParams,
}: {
  searchParams: Promise<{ id?: string }>;
}) {
  await requireSession();
  const index = await getReportIndex();
  const requestedId = (await searchParams).id;
  const selectedId = index.some((item) => item.report_id === requestedId)
    ? requestedId
    : index[0]?.report_id;
  const report = selectedId ? await getReportPayload(selectedId) : null;

  if (!index.length || !report) return <EmptyReportsPage />;

  return <ReportsScreen index={index} report={report} />;
}

function ReportsScreen({
  index,
  report,
}: {
  index: ReportIndexItem[];
  report: ReportPayload;
}) {
  const finalCount = index.filter((item) => item.document_status === "final").length;
  const validCount = index.filter((item) => item.summary.validation_valid).length;

  return (
    <div className="app-frame">
      <DesktopTopNavigation active="reports" />
      <DesktopSideNavigation active="reports" />

      <main className="dashboard-main reports-main">
        <MobileHeader />

        <header className="reports-title">
          <div>
            <span>REPORT ARCHIVE</span>
            <h1>리포트</h1>
            <p>생성 시점의 비식별 스냅샷과 판단 근거를 보관하고 다시 확인합니다.</p>
          </div>
          <div className={`reports-status ${report.summary.validation_valid ? "valid" : "review"}`}>
            <span>선택 리포트 QC</span>
            <strong>{report.summary.validation_valid ? "검증 통과" : "확인 필요"}</strong>
            <small>{formatDashboardDate(report.generated_at)} 기준</small>
          </div>
        </header>

        <section className="reports-summary" aria-label="리포트 아카이브 요약">
          <ReportSummary label="보관 리포트" value={`${index.length}건`} detail="최신 50건 유지" tone="archive" />
          <ReportSummary label="완성본" value={`${finalCount}건`} detail="최종 판단 문서" tone="final" />
          <ReportSummary label="QC 통과" value={`${validCount}건`} detail="숫자 기본 검증" tone="valid" />
          <ReportSummary label="현재 문서" value={kindLabel(report.report_kind)} detail={statusLabel(report.document_status)} tone="current" />
        </section>

        <section className="reports-layout">
          <aside className="surface reports-index">
            <header>
              <h2>리포트 목록</h2>
              <span>{index.length}건</span>
            </header>
            <nav aria-label="리포트 목록">
              {index.map((item) => (
                <Link
                  className={item.report_id === report.report_id ? "active" : ""}
                  href={`/reports?id=${encodeURIComponent(item.report_id)}`}
                  key={item.report_id}
                >
                  <div>
                    <span>{kindLabel(item.report_kind)}</span>
                    <b className={item.summary.validation_valid ? "valid" : "review"}>
                      {item.summary.validation_valid ? "QC 통과" : "확인 필요"}
                    </b>
                  </div>
                  <strong>{item.title}</strong>
                  <small>{formatDashboardDate(item.generated_at)} · {statusLabel(item.document_status)}</small>
                  <em>{formatSignedKrw(item.summary.change_krw)} · {formatPercent(item.summary.change_pct)}</em>
                </Link>
              ))}
            </nav>
          </aside>

          <article className="surface report-document">
            <header className="report-document-header">
              <div>
                <span>{kindLabel(report.report_kind)} · {statusLabel(report.document_status)}</span>
                <h2>{report.title}</h2>
                <p>{formatDashboardDate(report.generated_at)} 생성</p>
              </div>
              <div>
                <strong>{formatKrw(report.summary.total_value_krw)}</strong>
                <span className={tone(report.summary.change_krw)}>{formatSignedKrw(report.summary.change_krw)}</span>
              </div>
            </header>

            <div className="report-sections">
              {report.sections.map((section, indexValue) => (
                <section key={`${section.title}-${indexValue}`}>
                  <h3>{section.title}</h3>
                  <ul>{section.lines.map((line, lineIndex) => <li key={`${line}-${lineIndex}`}>{line}</li>)}</ul>
                </section>
              ))}
            </div>

            <ReportAppendix report={report} />
          </article>
        </section>

        <footer className="reports-footnote">
          <span>웹 리포트는 수량·평단·계좌 식별자를 제외한 비식별 요약만 보관합니다.</span>
          <span>리포트 본문과 상세 부록은 생성 시점 스냅샷을 기준으로 표시됩니다.</span>
        </footer>
      </main>

      <MobileBottomNavigation active="reports" />
    </div>
  );
}

function ReportAppendix({ report }: { report: ReportPayload }) {
  return (
    <details className="report-appendix">
      <summary>상세 부록 보기</summary>
      <div className="report-appendix-body">
        <section>
          <h3>자산별 스냅샷</h3>
          <div className="report-asset-table">
            {report.appendix.assets.map((asset) => (
              <article key={asset.symbol}>
                <div><strong>{asset.name}</strong><span>{asset.symbol}</span></div>
                <div><small>평가액</small><b>{formatKrw(asset.value_krw)}</b></div>
                <div><small>비중</small><b>{formatPercent(asset.weight_percent, false)}</b></div>
                <div><small>누계 수익률</small><b className={tone(asset.profit_loss_rate_percent)}>{formatPercent(asset.profit_loss_rate_percent)}</b></div>
              </article>
            ))}
          </div>
        </section>
        <section className="report-qc-grid">
          <div>
            <h3>제공자 상태</h3>
            {report.appendix.provider_status.map((provider) => (
              <p key={provider.provider}><span className={provider.used_fallback ? "review" : "valid"} />{provider.provider} · {provider.used_fallback ? "대체값 사용" : "정상"}</p>
            ))}
          </div>
          <div>
            <h3>검증 결과</h3>
            {report.appendix.validation_issues.length
              ? report.appendix.validation_issues.map((issue) => <p key={issue}>{issue}</p>)
              : <p>숫자·비중·변화율 기본 검증 통과</p>}
          </div>
        </section>
      </div>
    </details>
  );
}

function ReportSummary({
  label,
  value,
  detail,
  tone: itemTone,
}: {
  label: string;
  value: string;
  detail: string;
  tone: "archive" | "final" | "valid" | "current";
}) {
  return <article className={`reports-summary-item ${itemTone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function EmptyReportsPage() {
  return (
    <main className="empty-dashboard-page">
      <Brand />
      <section className="surface">
        <h1>업로드된 웹 리포트가 없습니다</h1>
        <p>Watchdog의 `sync-report` 또는 `complete-report --sync-dashboard`를 실행하면 생성 시점 리포트가 표시됩니다.</p>
      </section>
    </main>
  );
}

function kindLabel(value: "portfolio" | "weekly"): string {
  return value === "weekly" ? "주간 리포트" : "포트폴리오 리포트";
}

function statusLabel(value: "source" | "final"): string {
  return value === "final" ? "완성본" : "작성 원본";
}

function formatKrw(value: number): string {
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function formatSignedKrw(value: number): string {
  return `${value > 0 ? "+" : ""}${formatKrw(value)}`;
}

function formatPercent(value: number | null, signed = true): string {
  if (value === null) return "-";
  return `${signed && value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function tone(value: number | null): string {
  if (value === null || value === 0) return "neutral-text";
  return value > 0 ? "positive-text" : "negative-text";
}
