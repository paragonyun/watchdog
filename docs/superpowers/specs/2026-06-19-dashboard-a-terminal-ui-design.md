# Dashboard A Terminal UI Design

- Date: 2026-06-19
- Status: Approved by user via A안 selection
- Scope: Next.js dashboard visual upgrade only

## Goal

Rebuild the dashboard home screen around the approved A안, the institutional research terminal direction. The screen should look closer to the earlier mockup: dense, polished, data-forward on desktop, and compact but readable on mobile.

## Design

The dashboard home keeps the existing protected `/dashboard` route and existing uploaded payload contracts. No cloud-side account, quantity, average cost, or API key data is added.

Desktop layout:

- Fixed top navigation and side navigation remain.
- A six-card KPI strip shows total assets, period change, TWR, benchmark, cash, and attention count.
- The main hero grid shows investment performance, asset allocation versus target, and attention items.
- The lower grid shows portfolio groups, economic calendar, news-linked risks, related news, Codex investment opinion, latest report, and data status.

Mobile layout:

- Top mobile brand header and bottom navigation remain.
- Total assets and period change are shown first.
- Cards stack in priority order: performance, attention, allocation, portfolio, risk/news, opinion/report.
- Text must not overflow on narrow screens.

Visual direction:

- Quiet institutional palette using navy, blue, green, amber, and red.
- White panels with thin borders, restrained shadows, and denser typography.
- Simple CSS-based bars and comparison visuals, not a chart library.
- Rounded corners stay restrained at 8px or less for real dashboard panels.

## Data And States

The UI uses `buildDashboardView()` and `buildHomeInsights()` as the data boundary. Missing payloads show the existing empty state. Missing optional sections show clear empty cards instead of hiding the overall dashboard.

TWR is displayed only when the performance data exists. Otherwise, the performance panel explains that more ledger history is needed.

## Testing

- Add a server-rendering test that imports the dashboard home component and verifies the A안 terminal structure appears in markup.
- Keep existing dashboard view tests.
- Run `npm test` and `npm run build` inside `dashboard/`.
- Verify local desktop and mobile rendering with screenshots or browser checks.
