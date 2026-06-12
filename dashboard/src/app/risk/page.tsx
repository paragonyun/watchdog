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
import { buildRiskView, type RiskLevel, type RiskView } from "@/lib/risk-view";
import { getLatestDashboardPayloads } from "@/lib/storage";

export const dynamic = "force-dynamic";

export default async function RiskPage() {
  await requireSession();
  const { v1, v2 } = await getLatestDashboardPayloads();

  if (!v1 && !v2) {
    return <EmptyRiskPage />;
  }

  const view = buildDashboardView(v1, v2);
  return <RiskScreen view={view} risk={buildRiskView(view)} />;
}

function RiskScreen({ view, risk }: { view: DashboardView; risk: RiskView }) {
  return (
    <div className="app-frame">
      <DesktopTopNavigation active="risk" />
      <DesktopSideNavigation active="risk" />

      <main className="dashboard-main risk-main">
        <MobileHeader />

        <header className="risk-title">
          <div>
            <span>RISK MONITOR</span>
            <h1>리스크</h1>
            <p>현재 보유 비중과 누계 수익률을 기준으로 확인 우선순위를 계산합니다.</p>
          </div>
          <div className={`risk-posture ${risk.highestLevel}`}>
            <span>현재 위험 수준</span>
            <strong>{levelLabel(risk.highestLevel)}</strong>
            <small>{formatDashboardDate(view.generatedAt)} 기준</small>
          </div>
        </header>

        <section className="risk-kpis" aria-label="리스크 핵심 지표">
          <RiskKpi label="높은 위험" value={`${risk.highCount}건`} detail="즉시 근거 확인" level={risk.highCount ? "high" : "low"} />
          <RiskKpi label="중간 위험" value={`${risk.mediumCount}건`} detail="관찰 필요" level={risk.mediumCount ? "medium" : "low"} />
          <RiskKpi label="최대 종목 비중" value={formatPercent(risk.largestAsset?.weightPercent ?? null)} detail={risk.largestAsset?.name ?? "보유 종목 없음"} level={risk.checks.find((item) => item.id === "single")?.level ?? "low"} />
          <RiskKpi label="큰 손실 종목 노출" value={formatPercent(risk.lossExposureWeightPercent)} detail="-20% 이하 종목 합계" level={risk.checks.find((item) => item.id === "loss")?.level ?? "low"} />
          <RiskKpi label="목표 최대 이탈" value={formatPercentagePoint(risk.maxGroupDeviationPercentagePoints)} detail="자산군 기준" level={risk.checks.find((item) => item.id === "allocation")?.level ?? "low"} />
          <RiskKpi label="최대 낙폭" value={formatPercent(risk.maxDrawdownPct)} detail={view.performance.status === "insufficient_data" ? "성과 이력 부족" : "평가 이력 기준"} level={risk.checks.find((item) => item.id === "history")?.level ?? "low"} />
        </section>

        <section className="risk-layout">
          <section className="surface risk-check-panel">
            <PanelHeading title="확인 우선순위" meta={`${risk.highCount + risk.mediumCount}건 확인`} />
            <div className="risk-check-list">
              {risk.checks.map((check) => (
                <article className={`risk-check ${check.level}`} key={check.id}>
                  <span>{levelLabel(check.level)}</span>
                  <div>
                    <h2>{check.title}</h2>
                    <strong>{check.metric}</strong>
                    <p>{check.detail}</p>
                    <small>{check.threshold}</small>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="surface concentration-panel">
            <PanelHeading title="종목 집중도" meta={`상위 3종목 ${formatPercent(risk.topThreeWeightPercent)}`} />
            <div className="risk-bar-list">
              {risk.concentrationAssets.map((asset) => (
                <article key={asset.symbol}>
                  <div><strong>{asset.name}</strong><span>{asset.symbol}</span><b>{formatPercent(asset.weightPercent)}</b></div>
                  <div className="risk-bar-track"><i style={{ width: `${clamp(asset.weightPercent)}%` }} /></div>
                </article>
              ))}
            </div>
          </section>

          <section className="surface deviation-panel">
            <PanelHeading title="목표 비중 이탈" meta="현재 비중 vs 목표" />
            <div className="risk-deviation-list">
              {risk.groupDeviations.map((group) => (
                <article key={group.key}>
                  <div>
                    <strong>{group.label}</strong>
                    <span>현재 {formatPercent(group.weightPercent)} · 목표 {formatPercent(group.targetWeightPercent)}</span>
                    <b>{formatSignedPercentagePoint(group.targetDiffPercentagePoints)}</b>
                  </div>
                  <div className="risk-deviation-track">
                    <i className={group.key} style={{ width: `${clamp(group.weightPercent)}%` }} />
                    {group.targetWeightPercent !== null ? <em style={{ left: `${clamp(group.targetWeightPercent)}%` }} /> : null}
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="surface loss-panel">
            <PanelHeading title="큰 손실 종목" meta={`총자산의 ${formatPercent(risk.lossExposureWeightPercent)}`} />
            {risk.lossAssets.length ? (
              <div className="risk-loss-list">
                {risk.lossAssets.map((asset) => (
                  <article key={asset.symbol}>
                    <div><strong>{asset.name}</strong><span>{asset.symbol}</span></div>
                    <div><small>포트폴리오 비중</small><b>{formatPercent(asset.weightPercent)}</b></div>
                    <div><small>누계 수익률</small><b className="negative-text">{formatPercent(asset.profitLossRatePercent)}</b></div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="risk-empty">누계 수익률 -20% 이하 종목이 없습니다.</p>
            )}
          </section>
        </section>

        <footer className="risk-footnote">
          <span>이 화면은 현재 데이터에 대한 확인 우선순위이며 매수·매도 의견이 아닙니다.</span>
          <span>성과 이력이 부족하면 낙폭과 TWR 위험 판단은 제한됩니다.</span>
        </footer>
      </main>

      <MobileBottomNavigation active="risk" />
    </div>
  );
}

function RiskKpi({ label, value, detail, level }: { label: string; value: string; detail: string; level: RiskLevel }) {
  return <article className={`risk-kpi ${level}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function PanelHeading({ title, meta }: { title: string; meta: string }) {
  return <header className="panel-heading"><h2>{title}</h2><span>{meta}</span></header>;
}

function EmptyRiskPage() {
  return (
    <main className="empty-dashboard-page">
      <Brand />
      <section className="surface">
        <h1>리스크 데이터가 없습니다</h1>
        <p>Watchdog에서 대시보드 동기화를 실행하면 실제 보유 데이터 기반 리스크가 표시됩니다.</p>
      </section>
    </main>
  );
}

function levelLabel(level: RiskLevel): string {
  return level === "high" ? "높음" : level === "medium" ? "중간" : "낮음";
}

function formatPercent(value: number | null): string {
  return value === null ? "-" : `${value.toFixed(2)}%`;
}

function formatPercentagePoint(value: number | null): string {
  return value === null ? "-" : `${value.toFixed(2)}%p`;
}

function formatSignedPercentagePoint(value: number | null): string {
  return value === null ? "-" : `${value > 0 ? "+" : ""}${value.toFixed(2)}%p`;
}

function clamp(value: number): number {
  return Math.max(0, Math.min(100, value));
}
