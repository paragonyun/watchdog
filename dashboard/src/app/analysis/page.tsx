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

export const dynamic = "force-dynamic";

export default async function AnalysisPage() {
  await requireSession();
  const { v1, v2 } = await getLatestDashboardPayloads();
  if (!v1 && !v2) return <EmptyAnalysisPage />;
  return <AnalysisScreen view={buildDashboardView(v1, v2)} />;
}

function AnalysisScreen({ view }: { view: DashboardView }) {
  const availableReturns = view.assets.filter((asset) => asset.profitLossRatePercent !== null);
  const maxReturn = Math.max(10, ...availableReturns.map((asset) => Math.abs(asset.profitLossRatePercent ?? 0)));
  return (
    <div className="app-frame">
      <DesktopTopNavigation active="analysis" />
      <DesktopSideNavigation active="analysis" />
      <main className="dashboard-main analysis-main">
        <MobileHeader />
        <header className="analysis-title">
          <div><span>PERFORMANCE ANALYSIS</span><h1>성과 분석</h1><p>기간 수익률과 종목별 누계 수익률을 분리해 성과의 원천과 위험을 확인합니다.</p></div>
          <div><span>성과 계산 상태</span><strong>{performanceStatus(view.performance.status)}</strong><small>{formatDashboardDate(view.generatedAt)} 기준</small></div>
        </header>

        <section className="analysis-kpis">
          <AnalysisKpi label="누적 TWR" value={formatPercent(view.performance.cumulativeTwrPct)} detail="현금 유출입 영향을 제거한 기간 성과" />
          <AnalysisKpi label="당월 TWR" value={formatPercent(view.performance.monthTwrPct)} detail="이번 달 기간 성과" />
          <AnalysisKpi label="벤치마크" value={formatPercent(view.performance.benchmarkReturnPct)} detail="혼합 비교 기준" />
          <AnalysisKpi label="초과 성과" value={formatPercent(view.performance.excessReturnPct)} detail="포트폴리오 TWR - 벤치마크" />
          <AnalysisKpi label="최대 낙폭" value={formatPercent(view.performance.maxDrawdownPct)} detail="평가 이력 내 최대 하락" />
        </section>

        <section className="analysis-layout">
          <article className="surface analysis-return-panel">
            <header><div><span>RETURN ATTRIBUTION</span><h2>종목별 누계 수익률 분포</h2></div><small>매수원가 대비 · TWR 아님</small></header>
            {availableReturns.length ? <div className="analysis-return-list">{availableReturns.map((asset) => {
              const value = asset.profitLossRatePercent ?? 0;
              return <div key={asset.symbol}><span><strong>{asset.name}</strong><small>{asset.symbol} · 비중 {formatPercent(asset.weightPercent, false)}</small></span><div><i className={value >= 0 ? "positive" : "negative"} style={{ width: `${Math.max(3, Math.abs(value) / maxReturn * 100)}%` }} /></div><b className={value >= 0 ? "positive-text" : "negative-text"}>{formatPercent(value)}</b></div>;
            })}</div> : <p className="analysis-empty">누계 수익률 데이터가 없습니다.</p>}
          </article>

          <aside className="surface analysis-explainer">
            <header><span>METRIC GUIDE</span><h2>수익률 기준</h2></header>
            <section><strong>TWR</strong><p>입출금 영향을 제거한 기간 성과입니다. 포트폴리오 운용 성과와 벤치마크 비교에 사용합니다.</p></section>
            <section><strong>누계 수익률</strong><p>현재 평가액과 매수원가의 차이입니다. 개별 종목의 손익 상태를 보여주며 기간 성과와 다릅니다.</p></section>
            <section><strong>주간 변화</strong><p>주간 시작·종료 평가액 차이입니다. 입출금이 있으면 실제 투자 성과와 다를 수 있습니다.</p></section>
          </aside>
        </section>

        <footer className="analysis-footnote"><span>성과 이력이 부족하면 TWR·벤치마크·최대 낙폭은 표시하지 않습니다.</span><span>누계 수익률과 자산 비중을 혼동하지 않도록 별도 축으로 표시합니다.</span></footer>
      </main>
      <MobileBottomNavigation active="analysis" />
    </div>
  );
}

function AnalysisKpi({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <article><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function EmptyAnalysisPage() {
  return <main className="empty-dashboard-page"><Brand /><section className="surface"><h1>분석할 자산 데이터가 없습니다</h1><p>Watchdog 동기화 후 기간 성과와 종목별 누계 수익률을 확인할 수 있습니다.</p></section></main>;
}

function formatPercent(value: number | null, signed = true): string { return value === null ? "데이터 부족" : `${signed && value > 0 ? "+" : ""}${value.toFixed(2)}%`; }
function performanceStatus(value: string): string { return value === "confirmed" ? "확정" : value === "provisional" ? "잠정" : "데이터 부족"; }
