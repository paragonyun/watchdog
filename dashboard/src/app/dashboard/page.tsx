import { requireSession } from "@/lib/auth";
import { buildAssetSections, type AssetSection } from "@/lib/asset-groups";
import type { AssetSummary, DashboardPayload } from "@/lib/dashboard-payload";
import { getLatestDashboardData } from "@/lib/storage";

import { logoutAction } from "../login/actions";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  await requireSession();
  const { payload, source } = await getLatestDashboardData();

  if (!payload) {
    return <EmptyDashboardPage />;
  }

  const groups = payload.asset_groups;
  const total = payload.total_value_krw || 1;
  const assetSections = buildAssetSections(payload.assets, groups, total);

  return (
    <main className="dashboard-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Portfolio Watchdog</p>
          <h1>자산 현황</h1>
          {source === "sample" ? <p className="source-note">로컬 샘플 데이터</p> : null}
        </div>
        <form action={logoutAction}>
          <button className="secondary-button" type="submit">
            Sign out
          </button>
        </form>
      </header>

      <section className="metric-grid" aria-label="포트폴리오 요약">
        <Metric label="총 자산" value={formatKrw(payload.total_value_krw)} detail={formatDate(payload.generated_at)} />
        <Metric label="기간 변화" value={formatSignedKrw(payload.trend.change_krw)} detail={formatPercent(payload.trend.change_pct)} tone={payload.trend.change_krw >= 0 ? "positive" : "negative"} />
        <Metric label="스냅샷" value={`${payload.trend.snapshot_count}개`} detail={payload.report_kind === "weekly" ? "weekly" : "portfolio"} />
        <Metric label="Fallback" value={`${payload.provider_status.filter((item) => item.used_fallback).length}건`} detail={providerLabel(payload)} tone={payload.provider_status.some((item) => item.used_fallback) ? "warning" : "neutral"} />
      </section>

      <section className="content-band split">
        <div className="panel">
          <div className="panel-heading">
            <h2>자산군 비중</h2>
            <span>{formatKrw(total)}</span>
          </div>
          <div className="allocation-bar" aria-label="자산군 비중 막대">
            <span className="coin" style={{ width: `${percentage(groups.coin, total)}%` }} />
            <span className="equity" style={{ width: `${percentage(groups.equity, total)}%` }} />
            <span className="cash" style={{ width: `${percentage(groups.cash, total)}%` }} />
          </div>
          <div className="group-list">
            <GroupRow label="코인" value={groups.coin} total={total} tone="coin" />
            <GroupRow label="ISA" value={groups.equity} total={total} tone="equity" />
            <GroupRow label="현금" value={groups.cash} total={total} tone="cash" />
          </div>
        </div>

        <div className="panel">
          <div className="panel-heading">
            <h2>뉴스 영향</h2>
            <span>{payload.news_impacts.length}건</span>
          </div>
          <div className="news-list">
            {payload.news_impacts.slice(0, 4).map((item) => (
              <article className="news-item" key={`${item.title}-${item.impact_score}`}>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.reason}</p>
                </div>
                <span className={impactClass(item.impact_score)}>{item.impact_score > 0 ? `+${item.impact_score}` : item.impact_score}</span>
              </article>
            ))}
            {payload.news_impacts.length === 0 ? <p className="empty">확인된 주요 뉴스가 없습니다.</p> : null}
          </div>
        </div>
      </section>

      <section className="content-band">
        <div className="panel">
          <div className="panel-heading">
            <h2>자산별 현황</h2>
            <span>{payload.assets.length}개 종목</span>
          </div>
          <div className="asset-section-list">
            {assetSections.map((section) => (
              <AssetSectionPanel section={section} key={section.key} />
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value, detail, tone = "neutral" }: { label: string; value: string; detail: string; tone?: "neutral" | "positive" | "negative" | "warning" }) {
  return (
    <article className={`metric-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  );
}

function GroupRow({ label, value, total, tone }: { label: string; value: number; total: number; tone: "coin" | "equity" | "cash" }) {
  return (
    <div className="group-row">
      <span className={`dot ${tone}`} />
      <strong>{label}</strong>
      <span>{formatKrw(value)}</span>
      <em>{formatPercent(percentage(value, total))}</em>
    </div>
  );
}

function AssetSectionPanel({ section }: { section: AssetSection }) {
  return (
    <details className="asset-section">
      <summary>
        <span className={`dot ${section.key}`} />
        <strong>{section.label}</strong>
        <span>{formatKrw(section.value_krw)}</span>
        <em>{formatPercent(section.weight_percent)}</em>
        <small>{section.assets.length}개 종목</small>
      </summary>
      <div className="asset-section-body">
        {section.assets.length > 0 ? (
          <div className="asset-table" role="table" aria-label={`${section.label} 세부 종목`}>
            <div className="asset-row asset-head" role="row">
              <span>자산</span>
              <span>평가액</span>
              <span>비중</span>
              <span>누계 수익률</span>
              <span>출처</span>
            </div>
            {section.assets.map((asset) => (
              <AssetRow asset={asset} key={`${section.key}-${asset.symbol}`} />
            ))}
          </div>
        ) : (
          <p className="empty">등록된 세부 종목이 없습니다.</p>
        )}
      </div>
    </details>
  );
}

function EmptyDashboardPage() {
  return (
    <main className="dashboard-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Portfolio Watchdog</p>
          <h1>자산 현황</h1>
        </div>
        <form action={logoutAction}>
          <button className="secondary-button" type="submit">
            Sign out
          </button>
        </form>
      </header>

      <section className="content-band">
        <div className="panel empty-panel">
          <h2>업로드된 API 스냅샷이 없습니다</h2>
          <p>Watchdog에서 대시보드 동기화를 실행하면 최신 요약 데이터가 표시됩니다.</p>
        </div>
      </section>
    </main>
  );
}

function AssetRow({ asset }: { asset: AssetSummary }) {
  return (
    <div className="asset-row" role="row">
      <span>
        <strong>{asset.name}</strong>
        <em>{asset.symbol}</em>
      </span>
      <span>{formatKrw(asset.value_krw)}</span>
      <span>{formatPercent(asset.weight_percent)}</span>
      <span className={asset.profit_loss_rate_percent === null ? "" : asset.profit_loss_rate_percent >= 0 ? "positive-text" : "negative-text"}>{asset.profit_loss_rate_percent === null ? "-" : formatPercent(asset.profit_loss_rate_percent)}</span>
      <span>{asset.price_source}</span>
    </div>
  );
}

function providerLabel(payload: DashboardPayload): string {
  if (!payload.provider_status.length) {
    return "status unknown";
  }
  return payload.provider_status.map((item) => `${item.provider}${item.used_fallback ? " fallback" : " live"}`).join(" / ");
}

function impactClass(score: number): string {
  if (score > 0) {
    return "impact positive";
  }
  if (score < 0) {
    return "impact negative";
  }
  return "impact";
}

function percentage(value: number, total: number): number {
  return total <= 0 ? 0 : Math.max(0, Math.min(100, (value / total) * 100));
}

function formatKrw(value: number): string {
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function formatSignedKrw(value: number): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatKrw(value)}`;
}

function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "-";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "no data";
  }
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
