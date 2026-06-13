import {
  Brand,
  DesktopSideNavigation,
  DesktopTopNavigation,
  MobileBottomNavigation,
  MobileHeader,
} from "@/components/app-navigation";
import { requireSession } from "@/lib/auth";
import { buildDashboardView } from "@/lib/dashboard-view";
import { formatDashboardDate } from "@/lib/format-date";
import {
  buildOpinionView,
  type OpinionAction,
  type OpinionViewItem,
} from "@/lib/opinion-view";
import { buildNewsRiskView } from "@/lib/news-risk-view";
import { buildRiskView } from "@/lib/risk-view";
import { getLatestDashboardPayloads, getLatestNewsRiskPayload } from "@/lib/storage";

export const dynamic = "force-dynamic";

export default async function OpinionPage() {
  await requireSession();
  const [{ v1, v2 }, newsRiskPayload] = await Promise.all([
    getLatestDashboardPayloads(),
    getLatestNewsRiskPayload(),
  ]);

  if (!v1 && !v2) return <EmptyOpinionPage />;

  const dashboard = buildDashboardView(v1, v2);
  const opinions = buildOpinionView(
    dashboard,
    buildRiskView(dashboard),
    newsRiskPayload ? buildNewsRiskView(newsRiskPayload) : null,
  );

  return (
    <OpinionScreen
      generatedAt={dashboard.generatedAt}
      opinions={opinions}
    />
  );
}

function OpinionScreen({
  generatedAt,
  opinions,
}: {
  generatedAt: string | null;
  opinions: OpinionViewItem[];
}) {
  const reviewCount = opinions.filter((item) => item.action === "review").length;
  const observeCount = opinions.filter((item) => item.action === "observe").length;
  const maintainCount = opinions.filter((item) => item.action === "maintain").length;
  const posture: OpinionAction = reviewCount ? "review" : observeCount ? "observe" : "maintain";

  return (
    <div className="app-frame">
      <DesktopTopNavigation active="opinion" />
      <DesktopSideNavigation active="opinion" />

      <main className="dashboard-main opinion-main">
        <MobileHeader />

        <header className="opinion-title">
          <div>
            <span>DECISION SUPPORT</span>
            <h1>투자 의견</h1>
            <p>현재 수치 리스크와 뉴스 잠재 리스크를 연결해 다음 확인 행동을 정리합니다.</p>
          </div>
          <div className={`opinion-posture ${posture}`}>
            <span>현재 검토 상태</span>
            <strong>{actionLabel(posture)}</strong>
            <small>{formatDashboardDate(generatedAt)} 기준</small>
          </div>
        </header>

        <section className="opinion-summary" aria-label="투자 의견 요약">
          <OpinionSummary label="재검토" value={`${reviewCount}건`} detail="근거 우선 확인" action="review" />
          <OpinionSummary label="관찰" value={`${observeCount}건`} detail="지표 변화 추적" action="observe" />
          <OpinionSummary label="유지" value={`${maintainCount}건`} detail="현재 상태 유지" action="maintain" />
          <article className="opinion-summary-note">
            <span>운용 원칙</span>
            <strong>판단 보조</strong>
            <small>자동 주문 및 매매 지시 없음</small>
          </article>
        </section>

        <section className="opinion-board">
          <OpinionLane
            action="review"
            description="근거와 반대 근거를 우선 확인할 항목"
            items={opinions.filter((item) => item.action === "review")}
          />
          <OpinionLane
            action="observe"
            description="관찰 지표의 다음 변화를 추적할 항목"
            items={opinions.filter((item) => item.action === "observe")}
          />
          <OpinionLane
            action="maintain"
            description="현재 상태를 유지하며 정기 점검할 항목"
            items={opinions.filter((item) => item.action === "maintain")}
          />
        </section>

        <footer className="opinion-footnote">
          <span>의견은 현재 업로드된 비식별 요약 데이터와 뉴스 리스크를 기준으로 생성됩니다.</span>
          <span>확정 판단 전 근거·반대 근거·관찰 지표를 직접 확인하세요.</span>
        </footer>
      </main>

      <MobileBottomNavigation active="opinion" />
    </div>
  );
}

function OpinionSummary({
  label,
  value,
  detail,
  action,
}: {
  label: string;
  value: string;
  detail: string;
  action: OpinionAction;
}) {
  return (
    <article className={`opinion-summary-item ${action}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function OpinionLane({
  action,
  description,
  items,
}: {
  action: OpinionAction;
  description: string;
  items: OpinionViewItem[];
}) {
  return (
    <section className={`surface opinion-lane ${action}`}>
      <header>
        <div>
          <h2>{actionLabel(action)}</h2>
          <p>{description}</p>
        </div>
        <span>{items.length}건</span>
      </header>
      {items.length ? (
        <div className="opinion-list">
          {items.map((item, index) => (
            <OpinionCard initiallyOpen={index < 2} item={item} key={item.id} />
          ))}
        </div>
      ) : (
        <p className="opinion-empty">현재 해당 상태의 의견이 없습니다.</p>
      )}
    </section>
  );
}

function OpinionCard({
  item,
  initiallyOpen,
}: {
  item: OpinionViewItem;
  initiallyOpen: boolean;
}) {
  return (
    <details className={`opinion-card ${item.action}`} open={initiallyOpen}>
      <summary>
        <div className="opinion-card-tags">
          <span className={item.action}>{item.actionLabel}</span>
          <span>근거 신뢰도 {item.confidenceLabel}</span>
          {item.sourceLabels.map((source) => <span key={source}>{source}</span>)}
        </div>
        <h3>{item.title}</h3>
        <p>{item.summary}</p>
        <div className="opinion-related">
          <span>관련 자산</span>
          <strong>{item.relatedAssets.length ? item.relatedAssets.join(", ") : "포트폴리오 전체"}</strong>
        </div>
      </summary>
      <div className="opinion-detail">
        <OpinionDetail title="판단 근거" values={item.evidence} />
        <OpinionDetail title="반대 근거" values={item.counterEvidence} />
        <OpinionDetail title="다음 관찰 지표" values={item.watchIndicators} />
      </div>
    </details>
  );
}

function OpinionDetail({ title, values }: { title: string; values: string[] }) {
  return (
    <section>
      <h4>{title}</h4>
      {values.length ? <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul> : <p>현재 확인된 항목이 없습니다.</p>}
    </section>
  );
}

function EmptyOpinionPage() {
  return (
    <main className="empty-dashboard-page">
      <Brand />
      <section className="surface">
        <h1>투자 의견을 만들 자산 데이터가 없습니다</h1>
        <p>Watchdog에서 자산 현황을 동기화하면 수치 리스크와 뉴스 리스크를 연결한 의견이 표시됩니다.</p>
      </section>
    </main>
  );
}

function actionLabel(action: OpinionAction): string {
  return action === "review" ? "재검토" : action === "observe" ? "관찰" : "유지";
}
