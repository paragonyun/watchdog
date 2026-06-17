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
import { getLatestCalendarPayload, getLatestDashboardPayloads, getLatestNewsRiskPayload, getLatestOpinionPayload, getOpinionIndex, getReportIndex } from "@/lib/storage";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  await requireSession();
  const [{ v1, v2 }, news, opinion, opinionIndex, calendar, reports] = await Promise.all([
    getLatestDashboardPayloads(),
    getLatestNewsRiskPayload(),
    getLatestOpinionPayload(),
    getOpinionIndex(),
    getLatestCalendarPayload(),
    getReportIndex(),
  ]);
  if (!v1 && !v2) return <EmptySettingsPage />;
  return <SettingsScreen calendarAt={calendar?.generated_at ?? null} opinionCount={opinionIndex.length} view={buildDashboardView(v1, v2)} newsAt={news?.generated_at ?? null} opinionAt={opinion?.generated_at ?? null} reportCount={reports.length} />;
}

function SettingsScreen({ view, newsAt, opinionAt, opinionCount, calendarAt, reportCount }: { view: DashboardView; newsAt: string | null; opinionAt: string | null; opinionCount: number; calendarAt: string | null; reportCount: number }) {
  return (
    <div className="app-frame">
      <DesktopTopNavigation active="settings" />
      <DesktopSideNavigation active="settings" />
      <main className="dashboard-main settings-main">
        <MobileHeader />
        <header className="settings-title"><span>OPERATIONS</span><h1>데이터 및 운영 상태</h1><p>API 연결, 최신 동기화, 계산 상태와 클라우드 저장 범위를 확인합니다.</p></header>

        <section className="settings-grid">
          <article className="surface settings-panel">
            <header><h2>API 제공자 상태</h2><span>{view.providers.length}개</span></header>
            <div className="settings-status-list">{view.providers.map((provider) => <section key={provider.provider}><i className={provider.usedFallback ? "warning" : "healthy"} /><div><strong>{provider.provider.toUpperCase()}</strong><small>{provider.usedFallback ? "대체값 사용 중" : "실제 API 데이터"}</small></div><b>{providerStatus(provider.status)}</b></section>)}</div>
          </article>

          <article className="surface settings-panel">
            <header><h2>동기화 상태</h2><span>{view.status}</span></header>
            <div className="settings-sync-list">
              <SyncRow label="자산 스냅샷" value={formatDashboardDate(view.lastActualAt)} />
              <SyncRow label="뉴스 리스크" value={formatDashboardDate(newsAt)} />
              <SyncRow label="Codex 투자 의견" value={formatDashboardDate(opinionAt)} />
              <SyncRow label="투자 의견 이력" value={`${opinionCount}건`} />
              <SyncRow label="경제 일정" value={formatDashboardDate(calendarAt)} />
              <SyncRow label="보관 리포트" value={`${reportCount}건`} />
            </div>
          </article>

          <article className="surface settings-panel settings-policy">
            <header><h2>클라우드 저장 정책</h2><span>요약 데이터만</span></header>
            <ul><li>저장: 평가액, 비중, 수익률, 뉴스 요약, 판단 근거, 제공자 상태</li><li>제외: 수량, 평균 매수가, 계좌 식별자, API 키, 원문 오류 상세</li><li>투자 의견은 자동 주문에 연결되지 않으며 Codex가 작성한 결과만 표시</li></ul>
          </article>

          <article className="surface settings-panel settings-policy">
            <header><h2>운영 점검</h2><span>{view.attention.length ? "확인 필요" : "정상"}</span></header>
            {view.attention.length ? <ul>{view.attention.map((item) => <li key={item.title}><strong>{item.title}</strong> · {item.detail}</li>)}</ul> : <p>현재 데이터 최신성, 제공자 상태와 성과 계산에서 즉시 확인할 항목이 없습니다.</p>}
          </article>
        </section>
      </main>
      <MobileBottomNavigation active="settings" />
    </div>
  );
}

function SyncRow({ label, value }: { label: string; value: string }) { return <section><span>{label}</span><strong>{value}</strong></section>; }
function EmptySettingsPage() { return <main className="empty-dashboard-page"><Brand /><section className="surface"><h1>운영 상태 데이터가 없습니다</h1><p>Watchdog 동기화 후 API와 데이터 상태를 확인할 수 있습니다.</p></section></main>; }
function providerStatus(value: string): string { return value === "actual" ? "정상" : value === "fallback" ? "대체값" : value; }
