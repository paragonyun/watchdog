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
import { getLatestDashboardPayloads } from "@/lib/storage";

import { logoutAction } from "../login/actions";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  await requireSession();
  const { v1, v2 } = await getLatestDashboardPayloads();

  if (!v1 && !v2) {
    return <EmptyDashboardPage />;
  }

  return <DashboardHome view={buildDashboardView(v1, v2)} />;
}

function DashboardHome({ view }: { view: DashboardView }) {
  const cash = view.groups.find((group) => group.key === "cash");

  return (
    <div className="app-frame">
      <DesktopTopNavigation active="dashboard" />
      <DesktopSideNavigation active="dashboard" />

      <main className="dashboard-main">
        <MobileHeader />

        <section className="mobile-summary">
          <span>총자산</span>
          <div>
            <strong>{formatKrw(view.totalValueKrw)}</strong>
            <TrendValue value={view.periodChange.changeKrw} suffix="원" />
          </div>
          <small>{formatDate(view.generatedAt)} 기준</small>
        </section>

        <section className="kpi-strip" aria-label="핵심 투자 지표">
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

        <section className="hero-grid">
          <PerformancePanel view={view} />
          <AllocationPanel view={view} />
          <AttentionPanel view={view} />
        </section>

        <section className="insight-grid">
          <AssetPanel view={view} />
          <EmptyInsightPanel title="주요 경제 일정" description="연결된 실제 경제 일정 데이터가 없습니다." />
          <NewsPanel view={view} />
          <EmptyInsightPanel title="리포트" description="웹에서 조회 가능한 리포트가 아직 없습니다." />
          <EmptyInsightPanel title="투자 의견 및 논리" description="확정된 투자 의견이 아직 없습니다." wide />
          <DataStatusPanel view={view} />
        </section>

        <footer className="dashboard-footer">
          <span>TWR: 외부 현금흐름 영향을 제거한 시간가중수익률</span>
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
  tone?: "neutral" | "positive" | "negative" | "warning";
}) {
  return (
    <article className="kpi">
      <span>{label}</span>
      <strong className={`${valueTone}-text`}>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function PerformancePanel({ view }: { view: DashboardView }) {
  const values = [
    { label: "포트폴리오 TWR", value: view.performance.cumulativeTwrPct, tone: "portfolio" },
    { label: "혼합 벤치마크", value: view.performance.benchmarkReturnPct, tone: "benchmark" },
    { label: "초과성과", value: view.performance.excessReturnPct, tone: "excess" },
  ];
  const available = values.filter((item) => item.value !== null);
  const scale = Math.max(10, ...available.map((item) => Math.abs(item.value ?? 0)));

  return (
    <section className="surface performance-panel">
      <PanelHeading title="투자 성과 (TWR)" meta={statusLabel(view.performance.status)} />
      {available.length ? (
        <>
          <div className="performance-legend">
            {values.map((item) => (
              <span key={item.label}><i className={item.tone} />{item.label} <b>{formatPercent(item.value)}</b></span>
            ))}
          </div>
          <div className="comparison-chart" aria-label="TWR와 벤치마크 비교">
            {values.map((item) => (
              <div className="comparison-row" key={item.label}>
                <span>{item.label}</span>
                <div className="comparison-track">
                  <i className={item.tone} style={{ width: `${Math.max(2, Math.abs(item.value ?? 0) / scale * 100)}%` }} />
                </div>
                <strong className={tone(item.value) + "-text"}>{formatPercent(item.value)}</strong>
              </div>
            ))}
          </div>
          <div className="performance-note">
            <span>최대 낙폭 <strong>{formatPercent(view.performance.maxDrawdownPct)}</strong></span>
            <span>당월 TWR <strong>{formatPercent(view.performance.monthTwrPct)}</strong></span>
          </div>
        </>
      ) : (
        <EmptyState text="성과 계산에 필요한 평가 이력이 부족합니다." />
      )}
    </section>
  );
}

function AllocationPanel({ view }: { view: DashboardView }) {
  return (
    <section className="surface allocation-panel">
      <PanelHeading title="자산 배분 (현재 vs 목표)" meta="비중 · 목표 편차" />
      <div className="allocation-list">
        {view.groups.map((group) => (
          <div className="allocation-item" key={group.key}>
            <div>
              <strong>{group.label}</strong>
              <span>{formatKrw(group.valueKrw)}</span>
              <b>{formatPercent(group.weightPercent, false)}</b>
            </div>
            <div className="allocation-track">
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
    <section className="surface attention-panel">
      <PanelHeading title={`주의 필요 (${view.attention.length})`} meta="" />
      {view.attention.length ? (
        <div className="attention-list">
          {view.attention.map((item) => (
            <article key={item.title}>
              <span className={item.level}>{item.level === "high" ? "높음" : "중간"}</span>
              <div><strong>{item.title}</strong><p>{item.detail}</p></div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState text="현재 확인이 필요한 데이터 상태가 없습니다." />
      )}
    </section>
  );
}

function AssetPanel({ view }: { view: DashboardView }) {
  return (
    <section className="surface asset-panel">
      <PanelHeading title="포트폴리오" meta={`${view.assets.length}개 종목`} />
      <div className="compact-groups">
        {view.groups.map((group) => {
          const assets = view.assets.filter((asset) => asset.assetType === group.key);
          return (
            <details key={group.key}>
              <summary>
                <span className={`group-dot ${group.key}`} />
                <strong>{group.label}</strong>
                <span>{formatKrw(group.valueKrw)}</span>
                <b>{formatPercent(group.weightPercent, false)}</b>
              </summary>
              <div>
                {assets.length ? assets.map((asset) => (
                  <article className="compact-asset" key={asset.symbol}>
                    <span><strong>{asset.name}</strong><small>{asset.symbol}</small></span>
                    <span><b>{formatKrw(asset.valueKrw)}</b><small>평가액</small></span>
                    <span className={tone(asset.profitLossRatePercent) + "-text"}>
                      <b>{formatPercent(asset.profitLossRatePercent)}</b><small>누계 평가손익률</small>
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

function NewsPanel({ view }: { view: DashboardView }) {
  return (
    <section className="surface news-panel">
      <PanelHeading title="관련 뉴스" meta={`${view.news.length}건`} />
      {view.news.length ? (
        <div className="news-list">
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

function DataStatusPanel({ view }: { view: DashboardView }) {
  return (
    <section className="surface status-panel">
      <PanelHeading title="데이터 상태" meta={statusLabel(view.status)} />
      <div className="status-list">
        {view.providers.length ? view.providers.map((provider) => (
          <div key={provider.provider}>
            <span className={provider.usedFallback ? "status-dot warning" : "status-dot healthy"} />
            <strong>{provider.provider}</strong>
            <span>{statusLabel(provider.status)}</span>
          </div>
        )) : <EmptyState text="제공자 상태 정보가 없습니다." />}
      </div>
      <p className="status-footnote">마지막 실제 데이터: {formatDate(view.lastActualAt)}</p>
    </section>
  );
}

function EmptyInsightPanel({ title, description, wide = false }: { title: string; description: string; wide?: boolean }) {
  return (
    <section className={`surface empty-insight ${wide ? "wide" : ""}`}>
      <PanelHeading title={title} meta="" />
      <EmptyState text={description} />
    </section>
  );
}

function PanelHeading({ title, meta }: { title: string; meta: string }) {
  return <header className="panel-heading"><h2>{title}</h2>{meta ? <span>{meta}</span> : null}</header>;
}

function EmptyState({ text }: { text: string }) {
  return <div className="empty-state"><span>－</span><p>{text}</p></div>;
}

function EmptyDashboardPage() {
  return (
    <main className="empty-dashboard-page">
      <Brand />
      <section className="surface">
        <h1>업로드된 API 스냅샷이 없습니다</h1>
        <p>Watchdog에서 대시보드 동기화를 실행하면 실제 요약 데이터가 표시됩니다.</p>
        <form action={logoutAction}><button className="secondary-button" type="submit">Sign out</button></form>
      </section>
    </main>
  );
}

function TrendValue({ value, suffix }: { value: number | null; suffix: string }) {
  return <b className={tone(value) + "-text"}>{value === null ? "-" : `${signed(Math.round(value))}${suffix}`}</b>;
}

function tone(value: number | null): "positive" | "negative" | "neutral" {
  if (value === null || value === 0) return "neutral";
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
  };
  return labels[value] ?? value;
}

function clamp(value: number): number {
  return Math.max(0, Math.min(100, value));
}
