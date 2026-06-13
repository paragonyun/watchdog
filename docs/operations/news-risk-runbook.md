# Portfolio Watchdog 뉴스 리스크 운영 Runbook

## 기본 명령

```powershell
python -m portfolio_watchdog collect-news-risks --sync-dashboard
python -m portfolio_watchdog merge-news-risks --path snapshots/codex_news_risk.json --sync-dashboard
python -m portfolio_watchdog sync-news-risks --path snapshots/news_risk_latest.json
python -m portfolio_watchdog install-schedule
```

- `collect-news-risks`: 최근 72시간 RSS를 규칙 기반으로 분석하고 `snapshots/news_risk_latest.json`을 갱신합니다.
- `merge-news-risks`: Codex 심층 분석 결과를 기존 RSS 결과와 병합합니다.
- `sync-news-risks`: 기존 뉴스 리스크 파일을 다시 생성하지 않고 대시보드에 업로드합니다.
- `install-schedule`: 매시 10분에 `collect-news-risks --sync-dashboard`를 실행하는 Windows 작업을 등록합니다.

자동 RSS 분석은 OpenAI API를 호출하지 않으므로 별도 API 비용이 발생하지 않습니다. Codex 심층 분석은 정기 리포트 작성 또는 사용자가 요청한 시점에 수행하며, 결과는 `codex_news_risk_v1` 형식으로 저장한 뒤 병합합니다.

## 데이터 흐름

1. Watchdog이 자산 API로 현재 포트폴리오 평가를 계산합니다.
2. RSS 뉴스의 위험 신호를 보유 종목 직접 영향과 시장 전이 영향으로 분류합니다.
3. 개인정보 검사를 통과한 `news_risk_payload_v1`을 로컬에 원자적으로 저장합니다.
4. `--sync-dashboard` 사용 시 Vercel `/api/upload`로 전송합니다.
5. 대시보드는 Private Blob `dashboard/news-risk-latest.json`을 읽습니다.

뉴스 RSS와 자산 API는 독립적으로 실패 처리됩니다. 뉴스 수집 실패 시 기존 파일이 있으면 `delayed` 상태로 유지하고, 자산 API 또는 대시보드 동기화 실패가 뉴스 파일을 삭제하지 않습니다.

## 상태 해석

- `actual`: 최신 RSS 또는 Codex 결과가 정상 반영된 상태
- `delayed`: 뉴스 수집이 실패해 기존 결과를 유지하는 상태
- `refresh_required`: Codex 보강 결과가 오래됐거나 항목 재확인이 필요한 상태
- `new`: 최근 24시간 안에 생성 또는 갱신된 항목
- `active`: 최근 72시간 범위에서 계속 관찰 중인 항목

뉴스 리스크는 현재 위험 수준에 자동 합산하지 않으며 매수·매도 추천이 아닙니다. 사실, 예상 전이 경로, 관찰 지표, 반대 근거를 함께 확인합니다.

## 장애 확인 순서

1. `snapshots/news_risk_latest.json`이 존재하고 JSON 형식이 유효한지 확인합니다.
2. payload의 `status`, `rss_generated_at`, `codex_generated_at`을 확인합니다.
3. `WATCHDOG_DASHBOARD_UPLOAD_URL`과 `WATCHDOG_UPLOAD_TOKEN`이 로컬 `.env`에 설정됐는지 확인합니다.
4. Vercel의 `WATCHDOG_UPLOAD_TOKEN`과 로컬 값이 동일한지 확인합니다.
5. Vercel Blob 연결과 `BLOB_READ_WRITE_TOKEN` 설정을 확인합니다.
6. 파일은 정상이고 업로드만 실패했다면 `sync-news-risks`를 다시 실행합니다.
7. RSS 수집부터 다시 실행해야 하면 `collect-news-risks --sync-dashboard`를 실행합니다.

## Codex 심층 분석 병합

Codex 결과는 다음 조건을 만족해야 합니다.

- 최근 72시간의 확인 가능한 사실만 사용
- 한국은행, 금융당국, 거래소, Fed, 기업 공시 등 1차 출처 우선
- Reuters와 Bloomberg는 보조 출처로 사용
- 사실, 예상 전이 경로, 관찰 지표, 반대 근거를 분리
- 기존 항목의 판단이 바뀌면 `change_reason` 기록
- 뉴스 원문 전체, 수량, 평단, 계좌 식별자, API 키 제외

병합 후에는 다음 명령으로 검증과 업로드를 함께 수행합니다.

```powershell
python -m portfolio_watchdog merge-news-risks --path snapshots/codex_news_risk.json --sync-dashboard
```

## 클라우드 금지 정보

- 보유 수량과 평단
- 계좌 식별자와 주문 식별자
- API 키, 비밀키, 업로드 토큰
- 원본 API 응답과 상세 오류
- 뉴스 원문 전체

