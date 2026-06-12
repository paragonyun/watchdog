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
import { buildPortfolioSections } from "@/lib/portfolio-view";
import { getLatestDashboardPayloads } from "@/lib/storage";

export const dynamic = "force-dynamic";

export default async function PortfolioPage() {
  await requireSession();
  const { v1, v2 } = await getLatestDashboardPayloads();

  if (!v1 && !v2) {
    return <EmptyPortfolioPage />;
  }

  return <PortfolioScreen view={buildDashboardView(v1, v2)} />;
}

function PortfolioScreen({ view }: { view: DashboardView }) {
  const sections = buildPortfolioSections(view);

  return (
    <div className="app-frame">
      <DesktopTopNavigation active="portfolio" />
      <DesktopSideNavigation active="portfolio" />

      <main className="dashboard-main portfolio-main">
        <MobileHeader />

        <header className="portfolio-title">
          <div>
            <span>PORTFOLIO</span>
            <h1>포트폴리오</h1>
            <p>평가액, 포트폴리오 비중, 목표 편차와 종목별 누계 수익률을 구분해 확인합니다.</p>
          </div>
          <div>
            <strong>{formatKrw(view.totalValueKrw)}</strong>
            <span>{formatDashboardDate(view.generatedAt)} 기준</span>
          </div>
        </header>

        <section className="portfolio-overview" aria-label="자산군 요약">
          {sections.map((section) => (
            <article className={`portfolio-overview-item ${section.key}`} key={section.key}>
              <div>
                <span className={`group-dot ${section.key}`} />
                <strong>{section.label}</strong>
                <small>{section.assets.length}개 종목</small>
              </div>
              <b>{formatKrw(section.valueKrw)}</b>
              <dl>
                <div><dt>포트폴리오 비중</dt><dd>{formatPercent(section.weightPercent, false)}</dd></div>
                <div><dt>목표 편차</dt><dd className={deviationTone(section.targetDiffPercentagePoints)}>{formatPercentagePoint(section.targetDiffPercentagePoints)}</dd></div>
              </dl>
              <div className="portfolio-overview-track">
                <i style={{ width: `${clamp(section.weightPercent)}%` }} />
                {section.targetWeightPercent !== null ? <em style={{ left: `${clamp(section.targetWeightPercent)}%` }} /> : null}
              </div>
            </article>
          ))}
        </section>

        <section className="portfolio-allocation surface">
          <header>
            <div>
              <span>현재 자산 배분</span>
              <strong>전체 자산 {formatKrw(view.totalValueKrw)}</strong>
            </div>
            <div className="allocation-legend">
              {sections.map((section) => <span key={section.key}><i className={section.key} />{section.label} {formatPercent(section.weightPercent, false)}</span>)}
            </div>
          </header>
          <div className="portfolio-stacked-bar">
            {sections.map((section) => <i className={section.key} key={section.key} style={{ width: `${section.weightPercent}%` }} />)}
          </div>
        </section>

        <div className="portfolio-sections">
          {sections.map((section) => (
            <section className="surface portfolio-section" key={section.key}>
              <header className="portfolio-section-heading">
                <div>
                  <span className={`group-dot ${section.key}`} />
                  <h2>{section.label}</h2>
                  <small>{section.assets.length}개 종목</small>
                </div>
                <div>
                  <strong>{formatKrw(section.valueKrw)}</strong>
                  <span>전체의 {formatPercent(section.weightPercent, false)}</span>
                </div>
              </header>

              {section.assets.length ? (
                <div className="portfolio-table">
                  <div className="portfolio-table-head">
                    <span>자산</span>
                    <span>평가액</span>
                    <span>포트폴리오 비중</span>
                    <span>목표 편차</span>
                    <span>누계 수익률</span>
                    <span>데이터 출처</span>
                  </div>
                  {section.assets.map((asset) => (
                    <article className="portfolio-asset-row" key={asset.symbol}>
                      <span className="portfolio-asset-name"><strong>{asset.name}</strong><small>{asset.symbol}</small></span>
                      <Metric label="평가액" value={formatKrw(asset.valueKrw)} />
                      <Metric label="포트폴리오 비중" value={formatPercent(asset.weightPercent, false)} />
                      <Metric label="목표 편차" value={formatPercentagePoint(asset.targetDiffPercentagePoints)} tone={deviationTone(asset.targetDiffPercentagePoints)} />
                      <Metric label="누계 수익률" value={formatPercent(asset.profitLossRatePercent)} tone={tone(asset.profitLossRatePercent)} />
                      <Metric label="데이터 출처" value={providerForAsset(asset.assetType, asset.priceSource, view)} />
                    </article>
                  ))}
                </div>
              ) : (
                <p className="portfolio-empty">등록된 종목이 없습니다.</p>
              )}
            </section>
          ))}
        </div>

        <footer className="portfolio-footnote">
          <span>비중은 총자산 대비 평가액 비율입니다.</span>
          <span>목표 편차는 현재 비중과 설정 목표의 차이(%p), 누계 수익률은 종목별 매입원가 대비 평가손익률입니다.</span>
        </footer>
      </main>

      <MobileBottomNavigation active="portfolio" />
    </div>
  );
}

function EmptyPortfolioPage() {
  return (
    <main className="empty-dashboard-page">
      <Brand />
      <section className="surface">
        <h1>포트폴리오 데이터가 없습니다</h1>
        <p>Watchdog에서 대시보드 동기화를 실행하면 실제 자산 현황이 표시됩니다.</p>
      </section>
    </main>
  );
}

function Metric({ label, value, tone: valueTone = "neutral-text" }: { label: string; value: string; tone?: string }) {
  return <span className="portfolio-metric"><small>{label}</small><strong className={valueTone}>{value}</strong></span>;
}

function formatKrw(value: number): string {
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function formatPercent(value: number | null, signed = true): string {
  if (value === null || Number.isNaN(value)) return "-";
  return `${signed && value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatPercentagePoint(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%p`;
}

function tone(value: number | null): string {
  if (value === null || value === 0) return "neutral-text";
  return value > 0 ? "positive-text" : "negative-text";
}

function deviationTone(value: number | null): string {
  return value === null || value === 0 ? "neutral-text" : "warning-text";
}

function providerForAsset(assetType: string, legacySource: string | null, view: DashboardView): string {
  const providerName = assetType === "isa" ? "kis" : assetType === "coin" ? "upbit" : null;
  if (!providerName) return "수동";
  const provider = view.providers.find((item) => item.provider.toLowerCase() === providerName);
  if (provider) return provider.usedFallback ? `${providerName.toUpperCase()} 대체값` : providerName.toUpperCase();
  return legacySource ?? providerName.toUpperCase();
}

function clamp(value: number): number {
  return Math.max(0, Math.min(100, value));
}
