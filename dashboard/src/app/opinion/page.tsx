import {
  Brand,
  DesktopSideNavigation,
  DesktopTopNavigation,
  MobileBottomNavigation,
  MobileHeader,
} from "@/components/app-navigation";
import { requireSession } from "@/lib/auth";
import { formatDashboardDate } from "@/lib/format-date";
import type { OpinionAction, OpinionPayload } from "@/lib/opinion-payload";
import { getLatestOpinionPayload } from "@/lib/storage";

export const dynamic = "force-dynamic";

export default async function OpinionPage() {
  await requireSession();
  const payload = await getLatestOpinionPayload();

  if (!payload) return <EmptyOpinionPage />;
  return <OpinionScreen payload={payload} />;
}

function OpinionScreen({ payload }: { payload: OpinionPayload }) {
  const counts = {
    buy: payload.items.filter((item) => item.action === "buy").length,
    sell: payload.items.filter((item) => item.action === "sell").length,
    observe: payload.items.filter((item) => item.action === "observe").length,
  };

  return (
    <div className="app-frame">
      <DesktopTopNavigation active="opinion" />
      <DesktopSideNavigation active="opinion" />

      <main className="dashboard-main opinion-main">
        <MobileHeader />

        <header className="opinion-title">
          <div>
            <span>CODEX INVESTMENT VIEW</span>
            <h1>투자 의견</h1>
            <p>보유 자산과 시장 정보를 종합한 Codex 판단입니다. 근거와 반대 근거를 함께 확인하세요.</p>
          </div>
          <div className={`opinion-posture ${payload.portfolio_posture}`}>
            <span>포트폴리오 판단</span>
            <strong>{actionLabel(payload.portfolio_posture)}</strong>
            <small>{formatDashboardDate(payload.generated_at)} 기준</small>
          </div>
        </header>

        <section className="opinion-summary" aria-label="투자 의견 요약">
          <OpinionSummary label="매수" value={`${counts.buy}건`} detail="기대수익 대비 위험 우호적" action="buy" />
          <OpinionSummary label="매도" value={`${counts.sell}건`} detail="투자 논리 훼손 또는 위험 확대" action="sell" />
          <OpinionSummary label="관찰 필요" value={`${counts.observe}건`} detail="조건 확인 후 판단" action="observe" />
          <article className="opinion-summary-note">
            <span>Codex 종합 판단</span>
            <strong>{payload.summary}</strong>
            <small>자동 주문 및 투자 자문 아님</small>
          </article>
        </section>

        <section className="opinion-board">
          <OpinionLane action="buy" description="상승 여력과 촉매가 위험보다 우세한 자산" payload={payload} />
          <OpinionLane action="sell" description="투자 논리가 훼손됐거나 위험 축소가 필요한 자산" payload={payload} />
          <OpinionLane action="observe" description="핵심 조건을 확인한 뒤 판단해야 하는 자산" payload={payload} />
        </section>

        <footer className="opinion-footnote">
          <span>{payload.disclaimer}</span>
          <span>실제 거래 전 최신 가격, 세금, 거래 비용과 본인의 위험 허용도를 직접 확인하세요.</span>
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
  payload,
}: {
  action: OpinionAction;
  description: string;
  payload: OpinionPayload;
}) {
  const items = payload.items.filter((item) => item.action === action);
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
            <details className={`opinion-card ${item.action}`} key={item.id} open={index === 0}>
              <summary>
                <div className="opinion-card-tags">
                  <span className={item.action}>{actionLabel(item.action)}</span>
                  <span>확신도 {confidenceLabel(item.confidence)}</span>
                  {item.sources.map((source) => <span key={source.label}>{source.label}</span>)}
                </div>
                <h3>{item.name} <small>{item.symbol}</small></h3>
                <p>{item.thesis}</p>
                <div className="opinion-related">
                  <span>포지션 메모</span>
                  <strong>{item.suggested_position_note}</strong>
                </div>
              </summary>
              <div className="opinion-detail">
                <OpinionDetail title="판단 근거" values={item.evidence} />
                <OpinionDetail title="반대 근거" values={item.counter_evidence} />
                <OpinionDetail title="예상 촉매" values={item.catalysts} />
                <OpinionDetail title="판단 무효화 조건" values={item.invalidation_conditions} />
              </div>
            </details>
          ))}
        </div>
      ) : (
        <p className="opinion-empty">현재 해당 의견으로 분류된 자산이 없습니다.</p>
      )}
    </section>
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
        <h1>아직 생성된 Codex 투자 의견이 없습니다</h1>
        <p>Codex가 작성한 의견 JSON을 `sync-opinions --path &lt;파일&gt;`로 동기화하면 매수·매도·관찰 필요 판단이 표시됩니다.</p>
      </section>
    </main>
  );
}

function actionLabel(action: OpinionAction): string {
  return action === "buy" ? "매수" : action === "sell" ? "매도" : "관찰 필요";
}

function confidenceLabel(value: "low" | "medium" | "high"): string {
  return value === "high" ? "높음" : value === "medium" ? "보통" : "낮음";
}
