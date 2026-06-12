# Watchdog Dashboard v2 Core UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실제 v1·v2 Watchdog 데이터를 병합해 승인된 시안을 기반으로 한 반응형 홈 대시보드를 배포한다.

**Architecture:** 기존 `dashboard/latest.json` v1 Blob은 뉴스와 기간 변화용으로 유지하고, 새 `dashboard/v2-latest.json` Blob은 TWR·벤치마크·목표 편차·데이터 신선도용으로 저장한다. Next.js 서버 컴포넌트는 두 payload를 읽어 하나의 홈 화면을 구성하며, 데이터가 없는 섹션은 예시값 대신 명확한 빈 상태를 표시한다.

**Tech Stack:** Python 3.11, pytest, Next.js 16 App Router, React 19, TypeScript, Node test runner, Vercel Blob, CSS

---

## 범위와 성공 기준

- 홈 화면만 고품질로 완성하고 상세 메뉴 페이지는 만들지 않는다.
- 데스크톱에는 상단 내비게이션·사이드 레일, 모바일에는 상단 바·하단 내비게이션을 표시한다.
- 총자산, 기간 변화, TWR, 벤치마크, 현금, 주의 항목, 성과 비교, 자산 배분, 자산 상세, 뉴스, 데이터 상태를 실제 데이터로 표시한다.
- 투자 의견·경제 일정·리포트 데이터가 없으면 예시 데이터 없이 빈 상태를 표시한다.
- 비중 `%`, 수익률 `%`, 목표 편차 `%p`를 라벨과 위치로 구분한다.
- 기존 v1 업로드와 현재 배포를 깨뜨리지 않는다.
- 모바일 390px과 데스크톱 1440px에서 가로 스크롤과 겹침이 없어야 한다.

## 파일 구조

| 파일 | 책임 |
|---|---|
| `src/portfolio_watchdog/dashboard_data.py` | v2 payload 업로드 시 개인정보 계약 유지 |
| `src/portfolio_watchdog/app.py` | `sync-ledger` 결과를 선택적으로 v2 Blob에 업로드 |
| `src/portfolio_watchdog/cli.py` | `sync-ledger --sync-dashboard` 지원 |
| `tests/test_ledger_cli.py` | v2 동기화 CLI 회귀 테스트 |
| `dashboard/src/lib/dashboard-payload.ts` | v1·v2 타입과 검증 |
| `dashboard/src/lib/storage.ts` | v1·v2 Blob 분리 저장·병합 읽기 |
| `dashboard/src/lib/dashboard-view.ts` | 두 계약을 화면용 view model로 변환 |
| `dashboard/src/lib/format.ts` | 원화·퍼센트·시각 포맷 |
| `dashboard/src/app/api/upload/route.ts` | schema에 따라 v1·v2 Blob 저장 |
| `dashboard/src/app/dashboard/page.tsx` | 반응형 홈 화면 조립 |
| `dashboard/src/app/globals.css` | 시안 기반 데스크톱·모바일 디자인 |
| `dashboard/tests/dashboard-payload.test.ts` | v2 검증 테스트 |
| `dashboard/tests/storage.test.ts` | schema별 저장 경로 테스트 |
| `dashboard/tests/dashboard-view.test.ts` | 실제값·빈 상태·단위 분리 테스트 |

### Task 1: v2 클라우드 업로드 경로 연결

- [ ] `tests/test_ledger_cli.py`에 `sync-ledger --sync-dashboard`가 v2 payload를 업로드하는 실패 테스트를 작성한다.
- [ ] 테스트가 옵션 또는 업로드 호출 부재로 실패하는지 확인한다.
- [ ] `app.py`와 `cli.py`에 최소 연결을 구현한다. 업로드 함수는 기존 개인정보 검사와 Bearer token을 그대로 사용한다.
- [ ] Python 관련 테스트를 실행해 통과를 확인한다.

### Task 2: Next.js v1·v2 계약과 저장소 분리

- [ ] `dashboard-payload.test.ts`에 v2 허용·잘못된 payload 거부 테스트를 작성한다.
- [ ] `storage.test.ts`에 v1은 `dashboard/latest.json`, v2는 `dashboard/v2-latest.json`으로 선택되는 테스트를 작성한다.
- [ ] 실패를 확인한 뒤 union 타입, validator, schema별 Blob key 선택을 구현한다.
- [ ] 업로드 API가 두 schema를 모두 받아 각각 저장하도록 수정한다.
- [ ] 대시보드 단위 테스트를 실행한다.

### Task 3: 실제 데이터 기반 홈 view model

- [ ] `dashboard-view.test.ts`에 v1·v2 병합, v2 누락 호환, 비중·수익률·목표 편차 분리 테스트를 작성한다.
- [ ] 실패를 확인한 뒤 `dashboard-view.ts`와 `format.ts`를 구현한다.
- [ ] v1은 뉴스·기간 변화·가격 출처를, v2는 성과·목표 편차·신선도를 우선 사용한다.
- [ ] 없는 주의·의견·일정·리포트는 빈 배열로 유지한다.
- [ ] 관련 단위 테스트를 실행한다.

### Task 4: 승인 시안 기반 반응형 홈 UI

- [ ] view model이 섹션에 필요한 실제값과 빈 상태를 제공하는 테스트를 먼저 추가한다.
- [ ] `page.tsx`를 상단 내비게이션, 사이드 레일, KPI 스트립, 성과 비교, 자산 배분, 주의 항목, 자산 상세, 뉴스, 의견·일정·리포트 빈 상태로 재구성한다.
- [ ] 실제 시계열이 없는 동안 성과 그래프는 누적 TWR와 벤치마크 최종값 비교 시각화로 표시하고 선형 시계열을 조작하지 않는다.
- [ ] `globals.css`를 데스크톱 정보 밀도와 모바일 카드 흐름에 맞게 수정한다.
- [ ] 대시보드 테스트와 production build를 실행한다.

### Task 5: 전체 검증과 배포

- [ ] Python 전체 테스트를 실행한다.
- [ ] Next.js 전체 테스트와 production build를 실행한다.
- [ ] 로컬 서버에서 1440px·390px 브라우저 QA를 수행하고 가로 스크롤, 겹침, 빈 상태, 한글 표시를 확인한다.
- [ ] 실제 API로 `sync-ledger --sync-dashboard`와 기존 v1 `sync-dashboard`를 실행해 두 Blob을 갱신한다.
- [ ] 사용자 `.gitignore` 변경은 제외하고 변경사항을 커밋·push한다.
- [ ] Vercel production 배포 상태와 실제 로그인 후 홈 화면을 확인한다.

## 완료 조건

- v1·v2 payload가 각 Blob에 공존하고 업로드 API가 모두 허용한다.
- 운영 홈 화면에 가짜 투자정보가 없다.
- 성과·비중·목표 편차의 의미와 단위가 혼동되지 않는다.
- 실제 데이터가 없는 섹션은 빈 상태로 표시된다.
- Python 테스트, Next.js 테스트, Next.js build가 모두 통과한다.
- 배포된 데스크톱·모바일 홈 화면이 승인 시안의 정보 구조와 시각적 위계를 따른다.
