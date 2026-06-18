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
import { buildNewsRiskView, type NewsRiskView, type NewsRiskViewItem } from "@/lib/news-risk-view";
import { buildRiskView, type RiskLevel, type RiskView } from "@/lib/risk-view";
import { getLatestDashboardPayloads, getLatestNewsRiskPayload } from "@/lib/storage";

export const dynamic = "force-dynamic";

export default async function RiskPage() {
  await requireSession();
  const [{ v1, v2 }, newsRiskPayload] = await Promise.all([
    getLatestDashboardPayloads(),
    getLatestNewsRiskPayload(),
  ]);

  if (!v1 && !v2) {
    return newsRiskPayload ? <NewsOnlyRiskPage newsRisk={buildNewsRiskView(newsRiskPayload)} /> : <EmptyRiskPage />;
  }

  const view = buildDashboardView(v1, v2);
  return (
    <RiskScreen
      view={view}
      risk={buildRiskView(view)}
      newsRisk={newsRiskPayload ? buildNewsRiskView(newsRiskPayload) : null}
    />
  );
}

function NewsOnlyRiskPage({ newsRisk }: { newsRisk: NewsRiskView }) {
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
            <p>자산 현황 동기화를 기다리는 동안 최신 뉴스 기반 잠재 리스크를 표시합니다.</p>
          </div>
          <div className="risk-posture medium">
            <span>자산 데이터 상태</span>
            <strong>동기화 필요</strong>
            <small>뉴스 리스크는 독립적으로 갱신됩니다.</small>
          </div>
        </header>
        <NewsRiskSection newsRisk={newsRisk} />
      </main>
      <MobileBottomNavigation active="risk" />
    </div>
  );
}

function RiskScreen({ view, risk, newsRisk }: { view: DashboardView; risk: RiskView; newsRisk: NewsRiskView | null }) {
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

        <NewsRiskSection newsRisk={newsRisk} />

        <footer className="risk-footnote">
          <span>이 화면은 현재 데이터에 대한 확인 우선순위이며 매수·매도 의견이 아닙니다.</span>
          <span>성과 이력이 부족하면 낙폭과 TWR 위험 판단은 제한됩니다.</span>
        </footer>
      </main>

      <MobileBottomNavigation active="risk" />
    </div>
  );
}

function NewsRiskSection({ newsRisk }: { newsRisk: NewsRiskView | null }) {
  return (
    <section className="news-risk-section" aria-labelledby="news-risk-title">
      <header className="news-risk-section-heading">
        <div>
          <span>NEWS RISK RADAR</span>
          <h2 id="news-risk-title">뉴스 기반 잠재 리스크</h2>
          <p>최근 뉴스에서 보유 자산에 직접 닿는 위험과 시장을 통해 전이될 수 있는 위험을 분리해 보여줍니다.</p>
        </div>
        {newsRisk ? (
          <div className={`news-risk-status ${newsRisk.needsRefresh ? "refresh" : "actual"}`}>
            <span>분석 상태</span>
            <strong>{newsRisk.statusLabel}</strong>
            <small>RSS {formatDashboardDate(newsRisk.generatedAt)} · Codex {formatDashboardDate(newsRisk.codexGeneratedAt)}</small>
          </div>
        ) : null}
      </header>

      {newsRisk ? (
        <>
          <div className="news-risk-summary" aria-label="뉴스 리스크 요약">
            <NewsRiskSummary label="직접 영향" value={`${newsRisk.directCount}건`} detail="보유 종목 연결" tone="direct" />
            <NewsRiskSummary label="시장 전이" value={`${newsRisk.marketCount}건`} detail="자산군 연결" tone="market" />
            <NewsRiskSummary label="신규 발견" value={`${newsRisk.newCount}건`} detail="최근 수집 이후" tone="new" />
            <NewsRiskSummary
              label="심층 분석"
              value={newsRisk.codexGeneratedAt ? "반영됨" : "대기 중"}
              detail={newsRisk.codexGeneratedAt ? formatDashboardDate(newsRisk.codexGeneratedAt) : "RSS 규칙 분석만 표시"}
              tone={newsRisk.codexGeneratedAt ? "codex" : "refresh"}
            />
          </div>

          <section className={`surface news-risk-narrative ${newsRisk.narrative.tone}`}>
            <div>
              <span>오늘의 리스크 해석</span>
              <h3>{newsRisk.narrative.headline}</h3>
              <p>{newsRisk.narrative.summary}</p>
            </div>
            <ul>
              {newsRisk.narrative.nextActions.map((action) => <li key={action}>{action}</li>)}
            </ul>
          </section>

          <div className="news-risk-columns">
            <NewsRiskGroup
              description="보유 종목과 뉴스가 직접 연결된 위험"
              emptyText="현재 확인된 직접 영향 리스크가 없습니다."
              items={newsRisk.directRisks}
              title="직접 영향 리스크"
            />
            <NewsRiskGroup
              description="금리·환율·경기 등 시장 경로를 통한 잠재 위험"
              emptyText="현재 확인된 시장 전이 리스크가 없습니다."
              items={newsRisk.marketRisks}
              title="시장 전이 리스크"
            />
          </div>
        </>
      ) : (
        <section className="surface news-risk-unavailable">
          <strong>아직 업로드된 뉴스 리스크 분석이 없습니다.</strong>
          <p>Watchdog의 뉴스 리스크 동기화가 완료되면 이 영역에 RSS 규칙 분석과 Codex 심층 분석이 표시됩니다.</p>
        </section>
      )}
    </section>
  );
}

function NewsRiskSummary({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  tone: "direct" | "market" | "new" | "codex" | "refresh";
}) {
  return (
    <article className={`news-risk-summary-item ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function NewsRiskGroup({
  title,
  description,
  items,
  emptyText,
}: {
  title: string;
  description: string;
  items: NewsRiskViewItem[];
  emptyText: string;
}) {
  return (
    <section className="surface news-risk-group">
      <header>
        <div><h3>{title}</h3><p>{description}</p></div>
        <span>{items.length}건</span>
      </header>
      {items.length ? (
        <div className="news-risk-list">
          {items.map((item, index) => <NewsRiskCard item={item} initiallyOpen={index < 5} key={item.id} />)}
        </div>
      ) : (
        <p className="risk-empty">{emptyText}</p>
      )}
    </section>
  );
}

function NewsRiskCard({ item, initiallyOpen }: { item: NewsRiskViewItem; initiallyOpen: boolean }) {
  return (
    <details className={`news-risk-card ${item.priority}`} open={initiallyOpen}>
      <summary>
        <div className="news-risk-card-tags">
          <span className={`priority ${item.priority}`}>{item.priorityLabel}</span>
          <span className={`freshness ${item.freshness}`}>{item.freshnessLabel}</span>
          <span>{item.category}</span>
        </div>
        <h4>{item.title}</h4>
        <p>{item.potential_impact}</p>
        <div className="news-risk-card-meta">
          <span>{item.related_assets.length ? item.related_assets.join(", ") : groupLabels(item.related_asset_groups)}</span>
          <b>연결 비중 {formatPercent(item.related_asset_weight_pct)}</b>
        </div>
      </summary>
      <div className="news-risk-detail">
        <NewsRiskDetail title="확인된 사실" values={item.facts} />
        <NewsRiskDetail title="전이 경로" values={[item.transmission_path]} />
        <NewsRiskDetail title="관찰 지표" values={item.watch_indicators} />
        <NewsRiskDetail title="반대 근거" values={item.counter_evidence} />
        <NewsRiskDetail title="우선순위 근거" values={item.priority_reasons} />
        {item.change_reason ? <NewsRiskDetail title="변경 이유" values={[item.change_reason]} /> : null}
        <div className="news-risk-sources">
          <div>{item.sourceLabels.map((source) => <span key={source}>{source}</span>)}</div>
          <div>
            {item.source_links.map((link) => (
              <a href={link.url} key={`${link.title}-${link.url}`} rel="noreferrer" target="_blank">{link.title}</a>
            ))}
          </div>
        </div>
      </div>
    </details>
  );
}

function NewsRiskDetail({ title, values }: { title: string; values: string[] }) {
  if (!values.length) return null;
  return (
    <section>
      <h5>{title}</h5>
      <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul>
    </section>
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

function groupLabels(groups: Array<"isa" | "coin" | "cash">): string {
  const labels = { isa: "ISA", coin: "코인", cash: "현금" };
  return groups.map((group) => labels[group]).join(", ");
}
