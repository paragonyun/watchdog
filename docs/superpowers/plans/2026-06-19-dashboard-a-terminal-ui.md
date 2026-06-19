# Dashboard A Terminal UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved A안 institutional terminal dashboard home screen.

**Architecture:** Keep data loading in the existing server page and keep derived data in `dashboard-view.ts` / `home-insights.ts`. Export the dashboard home component for a focused server-rendering test, then update TSX and CSS only for the visual structure.

**Tech Stack:** Next.js App Router, React 19, TypeScript, Node test runner, CSS

---

### Task 1: Lock The A안 Markup Contract

**Files:**
- Modify: `dashboard/src/app/dashboard/page.tsx`
- Test: `dashboard/tests/dashboard-home-render.test.ts`

- [ ] Add a test that renders `DashboardHome` with sample `DashboardView` and empty `HomeInsights`.
- [ ] Verify the test fails because `DashboardHome` is not exported yet.
- [ ] Export `DashboardHome` and add stable section classes for terminal layout.
- [ ] Verify the test passes.

### Task 2: Implement Desktop Terminal Layout

**Files:**
- Modify: `dashboard/src/app/dashboard/page.tsx`
- Modify: `dashboard/src/app/globals.css`

- [ ] Update dashboard home markup to expose A안 sections: KPI strip, performance, allocation, attention, portfolio, calendar, risks, news, opinion, report, status.
- [ ] Replace the existing simple comparison bars with a more polished terminal-style performance panel using existing numeric fields.
- [ ] Update desktop CSS to match the approved A안: dense top strip, three-column hero grid, lower insight grid, thin borders, restrained shadows.
- [ ] Run the dashboard render test.

### Task 3: Implement Mobile Priority Flow

**Files:**
- Modify: `dashboard/src/app/dashboard/page.tsx`
- Modify: `dashboard/src/app/globals.css`

- [ ] Keep mobile header and bottom navigation.
- [ ] Show total assets and period change as the first mobile block.
- [ ] Stack panels in priority order with no horizontal overflow.
- [ ] Run `npm test`.

### Task 4: Build And Browser QA

**Files:**
- No source edits unless QA finds a regression.

- [ ] Run `npm run build` in `dashboard/`.
- [ ] Start the local dashboard dev server.
- [ ] Check desktop and mobile viewport screenshots for overflow, unreadable text, and missing live data.
- [ ] If QA finds layout issues, fix CSS and rerun tests/build.
