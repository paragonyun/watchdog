import Link from "next/link";

type ActivePage = "dashboard" | "portfolio" | "risk" | "opinion";

const topNavigation = [
  { label: "대시보드", href: "/dashboard", key: "dashboard" },
  { label: "포트폴리오", href: "/portfolio", key: "portfolio" },
  { label: "분석" },
  { label: "리스크", href: "/risk", key: "risk" },
  { label: "투자 의견", href: "/opinion", key: "opinion" },
  { label: "리포트" },
  { label: "설정" },
] as const;

const sideNavigation = [
  { icon: "⌂", label: "홈", href: "/dashboard", key: "dashboard" },
  { icon: "◷", label: "리스크", href: "/risk", key: "risk" },
  { icon: "▣", label: "포트폴리오", href: "/portfolio", key: "portfolio" },
  { icon: "◇", label: "의견", href: "/opinion", key: "opinion" },
  { icon: "▤", label: "리서치" },
  { icon: "○", label: "알림" },
  { icon: "⚙", label: "설정" },
] as const;

export function DesktopTopNavigation({ active }: { active: ActivePage }) {
  return (
    <header className="desktop-topnav">
      <Brand />
      <nav aria-label="주요 메뉴">
        {topNavigation.map((item) =>
          "href" in item ? (
            <Link className={item.key === active ? "active" : ""} href={item.href} key={item.label}>
              {item.label}
            </Link>
          ) : (
            <span key={item.label}>{item.label}</span>
          ),
        )}
      </nav>
      <div className="top-actions">
        <span className="icon-action" title="검색">⌕</span>
        <span className="icon-action notification" title="알림">○</span>
        <span className="profile-mark">JS</span>
      </div>
    </header>
  );
}

export function DesktopSideNavigation({ active }: { active: ActivePage }) {
  return (
    <aside className="desktop-sidenav" aria-label="보조 메뉴">
      {sideNavigation.map((item) =>
        "href" in item ? (
          <Link className={item.key === active ? "active" : ""} href={item.href} key={item.label}>
            <b>{item.icon}</b>
            <small>{item.label}</small>
          </Link>
        ) : (
          <span key={item.label}>
            <b>{item.icon}</b>
            <small>{item.label}</small>
          </span>
        ),
      )}
    </aside>
  );
}

export function MobileHeader() {
  return (
    <header className="mobile-header">
      <Brand />
      <div>
        <span className="icon-action" title="알림">○</span>
        <span className="icon-action" title="메뉴">☰</span>
      </div>
    </header>
  );
}

export function MobileBottomNavigation({ active }: { active: ActivePage }) {
  return (
    <nav className="mobile-bottom-nav" aria-label="모바일 메뉴">
      {sideNavigation.slice(0, 5).map((item) =>
        "href" in item ? (
          <Link className={item.key === active ? "active" : ""} href={item.href} key={item.label}>
            <b>{item.icon}</b>
            <small>{item.label}</small>
          </Link>
        ) : (
          <span key={item.label}><b>{item.icon}</b><small>{item.label}</small></span>
        ),
      )}
    </nav>
  );
}

export function Brand() {
  return (
    <Link className="brand" href="/dashboard">
      <span className="brand-shield">W</span>
      <strong>PORTFOLIO<br />WATCHDOG</strong>
    </Link>
  );
}
