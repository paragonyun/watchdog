import Link from "next/link";

type ActivePage = "dashboard" | "portfolio" | "analysis" | "risk" | "opinion" | "reports" | "settings";

const topNavigation = [
  { label: "대시보드", href: "/dashboard", key: "dashboard" },
  { label: "포트폴리오", href: "/portfolio", key: "portfolio" },
  { label: "분석", href: "/analysis", key: "analysis" },
  { label: "리스크", href: "/risk", key: "risk" },
  { label: "투자 의견", href: "/opinion", key: "opinion" },
  { label: "리포트", href: "/reports", key: "reports" },
  { label: "설정", href: "/settings", key: "settings" },
] as const;

const sideNavigation = [
  { icon: "⌂", label: "홈", href: "/dashboard", key: "dashboard" },
  { icon: "◷", label: "리스크", href: "/risk", key: "risk" },
  { icon: "▥", label: "분석", href: "/analysis", key: "analysis" },
  { icon: "▣", label: "포트폴리오", href: "/portfolio", key: "portfolio" },
  { icon: "◇", label: "의견", href: "/opinion", key: "opinion" },
  { icon: "▤", label: "리포트", href: "/reports", key: "reports" },
  { icon: "○", label: "알림" },
  { icon: "⚙", label: "설정", href: "/settings", key: "settings" },
] as const;

const mobileNavigation = sideNavigation.filter((item) =>
  "key" in item && ["dashboard", "portfolio", "analysis", "opinion", "reports"].includes(item.key),
);

export function DesktopTopNavigation({ active }: { active: ActivePage }) {
  return (
    <header className="desktop-topnav">
      <Brand />
      <nav aria-label="주요 메뉴">
        {topNavigation.map((item) => (
          <Link className={item.key === active ? "active" : ""} href={item.href} key={item.label}>
            {item.label}
          </Link>
        ))}
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
      {mobileNavigation.map((item) =>
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
