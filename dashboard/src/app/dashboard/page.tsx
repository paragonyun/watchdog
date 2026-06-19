import Link from "next/link";

import {
  Brand,
  DesktopSideNavigation,
  DesktopTopNavigation,
  MobileBottomNavigation,
  MobileHeader,
} from "@/components/app-navigation";
import { requireSession } from "@/lib/auth";
import { buildDashboardView, type DashboardView } from "@/lib/dashboard-view";
import { formatDashboardDate } from "@/lib/format-date";
import { buildHomeInsights, type HomeInsights } from "@/lib/home-insights";
import {
  getLatestCalendarPayload,
  getLatestDashboardPayloads,
  getLatestNewsRiskPayload,
  getLatestOpinionPayload,
  getOpinionIndex,
  getOpinionPayload,
  getReportIndex,
  getReportPayload,
} from "@/lib/storage";

import { logoutAction } from "../login/actions";

export const dynamic = "force-dynamic";

type Tone = "neutral" | "positive" | "negative" | "warning";

export default async function DashboardPage() {
  await requireSession();
  const [{ v1, v2 }, newsRisk, opinion, opinionIndex, reportIndex, calendar] = await Promise.all([
    getLatestDashboardPayloads(),
    getLatestNewsRiskPayload(),
    getLatestOpinionPayload(),
    getOpinionIndex(),
    getReportIndex(),
    getLatestCalendarPayload(),
  ]);

  if (!v1 && !v2) {
    return <EmptyDashboardPage />;
  }

  const reportId = reportIndex.find((item) => item.schema_version === "dashboard_report_v2")?.report_id ?? reportIndex[0]?.report_id;
  const previousReportId = reportIndex.find((item) => item.report_id !== reportId && item.schema_version === "dashboard_report_v2")?.report_id;
  const previousOpinionId = opinionIndex.find((item) => item.opinion_id !== opinion?.opinion_id)?.opinion_id;
  const [report, previousReport, previousOpinion] = await Promise.all([
    reportId ? getReportPayload(reportId) : null,
    previousReportId ? getReportPayload(previousReportId) : null,
    previousOpinionId ? getOpinionPayload(previousOpinionId) : null,
  ]);

  return (
    <DashboardHome
      insights={buildHomeInsights({ calendar, newsRisk, opinion, previousOpinion, report, previousReport })}
      view={buildDashboardView(v1, v2)}
    />
  );
}

export function DashboardHome({ view, insights }: { view: DashboardView; insights: HomeInsights }) {
  const cash = view.groups.find((group) => group.key === "cash");

  return (
    <div className="app-frame">
      <DesktopTopNavigation active="dashboard" />
      <DesktopSideNavigation active="dashboard" />

      <main className="dashboard-main dashboard-terminal">
        <MobileHeader />

        <section className="terminal-mobile-brief">
          <span>총자산</span>
          <div>
            <strong>{formatKrw(view.totalValueKrw)}</strong>
            <TrendValue value={view.periodChange.changeKrw} suffix="원" />
          </div>
          <small>{formatDate(view.generatedAt)} 기준</small>
        </section>

        <section className="terminal-kpi-strip" aria-label="핵심 자산 지표">
          <Kpi label="총자산" value={formatKrw(view.totalValueKrw)} detail={`${formatDate(view.generatedAt)} 기준`} />
          <Kpi
            label="기간 변화"
            value={formatSignedKrw(view.periodChange.changeKrw)}
            detail={formatPercent(view.periodChange.changePct)}
            tone={tone(view.periodChange.changeKrw)}
          />
          <Kpi
            label="투자 성과 (TWR)"
            value={formatPercent(view.performance.cumulativeTwrPct)}
            detail={`당월 ${formatPercent(view.performance.monthTwrPct)}`}
            tone={tone(view.performance.cumulativeTwrPct)}
          />
          <Kpi
            label="벤치마크"
            value={formatPercent(view.performance.benchmarkReturnPct)}
            detail={`초과성과 ${formatPercent(view.performance.excessReturnPct)}`}
            tone={tone(view.performance.excessReturnPct)}
          />
          <Kpi
            label="현금 및 예수금"
            value={formatKrw(cash?.valueKrw ?? 0)}
            detail={`전체의 ${formatPercent(cash?.weightPercent ?? 0, false)}`}
          />
          <Kpi
            label="주의 필요"
            value={`${view.attention.length}건`}
            detail={view.attention.length ? "확인 필요" : "특이사항 없음"}
            tone={view.attention.length ? "warning" : "positive"}
          />
        </section>

        <section className="terminal-hero-grid">
          <PerformancePanel view={view} />
          <AllocationPanel view={view} />
          <AttentionPanel view={view} />
        </section>

        <section className="terminal-insight-grid">
          <AssetPanel view={view} />
          <CalendarPanel insight={insights.calendar} />
          <NewsRiskPanel insight={insights.newsRisk} />
          <NewsPanel view={view} />
          <OpinionPanel insight={insights.opinion} />
          <ReportPanel insight={insights.report} />
          <DataStatusPanel view={view} />
        </section>

        <footer className="terminal-footer">
          <span>TWR은 입출금 영향을 제거한 시간가중수익률입니다.</span>
          <span>데이터 기준: {formatDate(view.generatedAt)}</span>
        </footer>
      </main>

      <MobileBottomNavigation active="dashboard" />
    </div>
  );
}

function Kpi({
  label,
  value,
  detail,
  tone: valueTone = "neutral",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: Tone;
}) {
  return (
    <article className="terminal-kpi-card">
      <span>{label}</span>
      <strong className={`${valueTone}-text`}>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function PerformancePanel({ view }: { view: DashboardView }) {
  const values = [
    { label: "포트폴리오", value: view.performance.cumulativeTwrPct, className: "portfolio" },
    { label: "벤치마크", value: view.performance.benchmarkReturnPct, className: "benchmark" },
    { label: "초과성과", value: view.performance.excessReturnPct, className: "excess" },
  ];
  const available = values.filter((item) => item.value !== null);
  const scale = Math.max(10, ...available.map((item) => Math.abs(item.value ?? 0)));

  return (
    <section className="terminal-panel terminal-performance-panel">
      <PanelHeading title="투자 성과 (TWR)" meta={statusLabel(view.performance.status)} />
      {available.length ? (
        <>
          <div className="terminal-performance-headline">
            <span>포트폴리오</span>
            <strong className={tone(view.performance.cumulativeTwrPct) + "-text"}>{formatPercent(view.performance.cumulativeTwrPct)}</strong>
            <small>벤치마크 대비 {formatPercent(view.performance.excessReturnPct)}</small>
          </div>
          <div className="terminal-performance-chart" aria-label="TWR과 벤치마크 비교">
            {values.map((item) => (
              <div className="terminal-comparison-row" key={item.label}>
                <span>{item.label}</span>
                <div className="terminal-comparison-track">
                  <i className={item.className} style={{ width: `${Math.max(2, Math.abs(item.value ?? 0) / scale * 100)}%` }} />
                </div>
                <strong className={tone(item.value) + "-text"}>{formatPercent(item.value)}</strong>
              </div>
            ))}
          </div>
          <div className="terminal-performance-note">
            <span>당월 TWR <strong>{formatPercent(view.performance.monthTwrPct)}</strong></span>
            <span>최대 낙폭 <strong>{formatPercent(view.performance.maxDrawdownPct)}</strong></span>
          </div>
        </>
      ) : (
        <EmptyState text="투자 성과는 거래·입출금 이력이 더 쌓이면 표시됩니다." />
      )}
    </section>
  );
}

function AllocationPanel({ view }: { view: DashboardView }) {
  return (
    <section className="terminal-panel terminal-allocation-panel">
      <PanelHeading title="자산 배분 (vs 목표)" meta="현재 비중과 목표 차이" />
      <div className="terminal-allocation-list">
        {view.groups.map((group) => (
          <div className="terminal-allocation-item" key={group.key}>
            <div>
              <strong>{group.label}</strong>
              <span>{formatKrw(group.valueKrw)}</span>
              <b>{formatPercent(group.weightPercent, false)}</b>
            </div>
            <div className="terminal-allocation-track">
              <i className={group.key} style={{ width: `${clamp(group.weightPercent)}%` }} />
              {group.targetWeightPercent !== null ? (
                <em style={{ left: `${clamp(group.targetWeightPercent)}%` }} title={`목표 ${formatPercent(group.targetWeightPercent, false)}`} />
              ) : null}
            </div>
            <small>
              {group.targetDiffPercentagePoints === null
                ? "목표 비중 데이터 없음"
                : `목표 대비 ${formatPercentagePoint(group.targetDiffPercentagePoints)}`}
            </small>
          </div>
        ))}
      </div>
    </section>
  );
}

function AttentionPanel({ view }: { view: DashboardView }) {
  return (
    <section className="terminal-panel terminal-attention-panel">
      <PanelHeading title={`주의 필요 (${view.attention.length})`} meta={view.attention.length ? "확인 필요" : ""} />
      {view.attention.length ? (
        <div className="terminal-attention-list">
          {view.attention.map((item) => (
            <article key={item.title}>
              <span className={item.level}>{item.level === "high" ? "높음" : "중간"}</span>
              <div>
                <strong>{item.title}</strong>
                <p>{item.detail}</p>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState text="현재 즉시 확인할 주의 항목은 없습니다." />
      )}
    </section>
  );
}

function AssetPanel({ view }: { view: DashboardView }) {
  return (
    <section className="terminal-panel terminal-asset-panel">
      <PanelHeading title="포트폴리오" meta={`${view.assets.length}개 종목`} />
      <div className="terminal-group-list">
        {view.groups.map((group) => {
          const assets = view.assets.filter((asset) => asset.assetType === group.key);
          return (
            <details key={group.key}>
              <summary>
                <span className={`terminal-group-dot ${group.key}`} />
                <strong>{group.label}</strong>
                <span>{formatKrw(group.valueKrw)}</span>
                <b>{formatPercent(group.weightPercent, false)}</b>
              </summary>
              <div>
                {assets.length ? assets.map((asset) => (
                  <article className="terminal-asset-row" key={asset.symbol}>
                    <span>
                      <strong>{asset.name}</strong>
                      <small>{asset.symbol}</small>
                    </span>
                    <span>
                      <b>{formatKrw(asset.valueKrw)}</b>
                      <small>평가액</small>
                    </span>
                    <span className={tone(asset.profitLossRatePercent) + "-text"}>
                      <b>{formatPercent(asset.profitLossRatePercent)}</b>
                      <small>누계 평가손익률</small>
                    </span>
                  </article>
                )) : <EmptyState text="등록된 세부 종목이 없습니다." />}
              </div>
            </details>
          );
        })}
      </div>
    </section>
  );
}

function CalendarPanel({ insight }: { insight: HomeInsights["calendar"] }) {
  return (
    <section className="terminal-panel terminal-calendar-panel">
      <PanelHeading title="주요 촉매 일정" meta={insight ? `${insight.totalCount}건 · 높음 ${insight.highCount}건` : "일정 대기"} />
      {insight && insight.items.length ? (
        <div className="terminal-calendar-list">
          {insight.items.map((item) => (
            <article key={item.id}>
              <time dateTime={item.startsAt}>{formatDate(item.startsAt)}</time>
              <div>
                <span className={item.importance}>{item.importanceLabel}</span>
                <strong>{item.title}</strong>
                <p>{item.expectedImpact}</p>
                <small>{item.country} · {item.category} · {item.watchNote}</small>
              </div>
            </article>
          ))}
        </div>
      ) : <EmptyState text="아직 업로드된 경제 일정이 없습니다." />}
    </section>
  );
}

function NewsRiskPanel({ insight }: { insight: HomeInsights["newsRisk"] }) {
  return (
    <section className="terminal-panel terminal-risk-panel">
      <PanelLinkHeading href="/risk" meta={insight ? `${insight.totalCount}건 · 신규 ${insight.newCount}건` : "분석 대기"} title="현재 리스크" />
      {insight ? (
        <div className="terminal-risk-list">
          {insight.items.map((item) => (
            <article key={item.id}>
              <span className={item.priority}>{item.priorityLabel}</span>
              <div>
                <strong>{item.title}</strong>
                <p>{item.impact}</p>
              </div>
            </article>
          ))}
        </div>
      ) : <EmptyState text="아직 업로드된 뉴스 기반 리스크가 없습니다." />}
    </section>
  );
}

function NewsPanel({ view }: { view: DashboardView }) {
  return (
    <section className="terminal-panel terminal-news-panel">
      <PanelHeading title="관련 뉴스" meta={`${view.news.length}건`} />
      {view.news.length ? (
        <div className="terminal-news-list">
          {view.news.slice(0, 5).map((news) => (
            <article key={`${news.title}-${news.impact_score}`}>
              <div>
                <strong>{news.title}</strong>
                <p>{news.reason}</p>
              </div>
              <span className={tone(news.impact_score) + "-text"}>{signed(news.impact_score)}</span>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState text="현재 연결된 관련 뉴스가 없습니다." />
      )}
    </section>
  );
}

function OpinionPanel({ insight }: { insight: HomeInsights["opinion"] }) {
  return (
    <section className="terminal-panel terminal-opinion-panel">
      <PanelLinkHeading href="/opinion" meta={insight ? `${formatDate(insight.generatedAt)} 기준` : "분석 대기"} title="Codex 투자 의견" />
      {insight ? (
        <>
          <div className={`terminal-opinion-posture ${insight.posture}`}>
            <span>포트폴리오 판단</span>
            <strong>{insight.postureLabel}</strong>
            <p>{insight.summary}</p>
            {insight.changeSummary ? <small>변화: {insight.changeSummary}</small> : null}
          </div>
          <div className="terminal-opinion-counts">
            <span><b className="buy">{insight.counts.buy}</b>매수</span>
            <span><b className="sell">{insight.counts.sell}</b>매도</span>
            <span><b className="observe">{insight.counts.observe}</b>관찰필요</span>
          </div>
          <div className="terminal-opinion-list">
            {insight.items.map((item) => (
              <article key={item.id}>
                <span className={item.action}>{item.actionLabel}</span>
                <div>
                  <strong>{item.name} <small>{item.symbol}</small></strong>
                  <p>{item.thesis}</p>
                </div>
              </article>
            ))}
          </div>
        </>
      ) : <EmptyState text="아직 생성된 Codex 투자 의견이 없습니다." />}
    </section>
  );
}

function ReportPanel({ insight }: { insight: HomeInsights["report"] }) {
  return (
    <section className="terminal-panel terminal-report-panel">
      <PanelLinkHeading href={insight ? `/reports?id=${encodeURIComponent(insight.id)}` : "/reports"} meta={insight?.kindLabel ?? "리포트 대기"} title="최신 리서치" />
      {insight ? (
        <>
          <div className={`terminal-report-stance ${insight.stance ?? "source"}`}>
            <span>{insight.stanceLabel}</span>
            <b>{insight.validationValid ? "QC 통과" : "검증 필요"}</b>
          </div>
          <h3>{insight.title}</h3>
          <strong>{insight.headline}</strong>
          {insight.changeSummary ? <p className="terminal-change-note">변화: {insight.changeSummary}</p> : null}
          <ul>{insight.summaryPoints.map((item) => <li key={item}>{item}</li>)}</ul>
          <small>{formatDate(insight.generatedAt)} 생성</small>
        </>
      ) : <EmptyState text="웹에서 조회 가능한 완성 리포트가 아직 없습니다." />}
    </section>
  );
}

function DataStatusPanel({ view }: { view: DashboardView }) {
  return (
    <section className="terminal-panel terminal-status-panel">
      <PanelHeading title="데이터 상태" meta={statusLabel(view.status)} />
      <div className="terminal-status-list">
        {view.providers.length ? view.providers.map((provider) => (
          <div key={provider.provider}>
            <span className={provider.usedFallback ? "terminal-status-dot warning" : "terminal-status-dot healthy"} />
            <strong>{provider.provider}</strong>
            <span>{statusLabel(provider.status)}</span>
          </div>
        )) : <EmptyState text="제공자 상태 정보가 없습니다." />}
      </div>
      <p className="terminal-status-footnote">마지막 실제 데이터: {formatDate(view.lastActualAt)}</p>
    </section>
  );
}

function PanelHeading({ title, meta }: { title: string; meta?: string }) {
  return (
    <header className="terminal-panel-heading">
      <h2>{title}</h2>
      {meta ? <span>{meta}</span> : null}
    </header>
  );
}

function PanelLinkHeading({ title, meta, href }: { title: string; meta: string; href: string }) {
  return (
    <header className="terminal-panel-heading">
      <h2>{title}</h2>
      <Link href={href}>{meta}</Link>
    </header>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="terminal-empty-state">
      <span>i</span>
      <p>{text}</p>
    </div>
  );
}

function EmptyDashboardPage() {
  return (
    <main className="empty-dashboard-page">
      <Brand />
      <section className="terminal-panel">
        <h1>업로드된 API 스냅샷이 없습니다</h1>
        <p>Watchdog에서 대시보드 동기화를 실행하면 최신 요약 데이터가 표시됩니다.</p>
        <form action={logoutAction}><button className="secondary-button" type="submit">Sign out</button></form>
      </section>
    </main>
  );
}

function TrendValue({ value, suffix }: { value: number | null; suffix: string }) {
  return <b className={tone(value) + "-text"}>{value === null ? "-" : `${signed(Math.round(value))}${suffix}`}</b>;
}

function tone(value: number | null): Tone {
  if (value === null || value === 0 || Number.isNaN(value)) return "neutral";
  return value > 0 ? "positive" : "negative";
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

function formatKrw(value: number): string {
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function formatSignedKrw(value: number | null): string {
  return value === null ? "-" : `${value > 0 ? "+" : ""}${formatKrw(value)}`;
}

function formatPercent(value: number | null, signedValue = true): string {
  if (value === null || Number.isNaN(value)) return "-";
  return `${signedValue && value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatPercentagePoint(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%p`;
}

function formatDate(value: string | null): string {
  return formatDashboardDate(value);
}

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    actual: "실제 데이터",
    estimated: "추정 데이터",
    stale: "갱신 필요",
    fallback: "대체값 사용",
    confirmed: "확정",
    provisional: "잠정",
    insufficient_data: "데이터 부족",
    unavailable: "데이터 없음",
  };
  return labels[value] ?? value;
}

function clamp(value: number): number {
  return Math.max(0, Math.min(100, value));
}
