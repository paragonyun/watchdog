# Portfolio Watchdog

개인 포트폴리오를 주기적으로 조회하고 텔레그램으로 자산 현황, 뉴스 체크, 위클리 리포트 자료를 보내는 Windows 중심 도구입니다.

## 주요 명령

```powershell
python -m portfolio_watchdog setup
python -m portfolio_watchdog check-config
python -m portfolio_watchdog run
python -m portfolio_watchdog check-news
python -m portfolio_watchdog weekly-report
python -m portfolio_watchdog weekly-source
python -m portfolio_watchdog portfolio-source
python -m portfolio_watchdog render-report-pdf --path reports\weekly_report_final_YYYYMMDD_HHMM.md
python -m portfolio_watchdog send-report-document --path reports\weekly_report_final_YYYYMMDD_HHMM.pdf
python -m portfolio_watchdog complete-report --path reports\portfolio_report_final_YYYYMMDD_HHMM.md --sync-dashboard
python -m portfolio_watchdog sync-dashboard --path reports\portfolio_report_source_YYYYMMDD_HHMM.json
python -m portfolio_watchdog sync-ledger --sync-dashboard
python -m portfolio_watchdog add-cash-flow --amount 1000000 --occurred-at 2026-06-06T12:00:00 --memo "cash deposit"
python -m portfolio_watchdog performance-summary
python -m portfolio_watchdog send-message-file --path reports\hourly_news_codex_YYYYMMDD_HHMM.html
python -m portfolio_watchdog send-sample-reports
python -m portfolio_watchdog install-schedule
```

EXE 빌드:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

빌드 결과:

```text
dist\PortfolioWatchdog\PortfolioWatchdog.exe
```

## 설정

`.env.example`을 `.env`로 복사한 뒤 Telegram, Upbit, KIS 키를 입력합니다. OpenAI 키는 선택사항이며, 비워두면 비용 없는 RSS/규칙 기반 뉴스 분석을 사용합니다.

```powershell
Copy-Item .env.example .env
Copy-Item config\config.example.yaml config\config.yaml
```

## PC 재시작 후 자동화 점검

PC를 껐다 켠 뒤에는 아래 순서로 확인합니다.

```powershell
python -m portfolio_watchdog check-config
python -m portfolio_watchdog send-test-alert
```

체크리스트:

- 인터넷 연결 확인
- Codex Desktop 실행 및 로그인 상태 확인
- 이 프로젝트 폴더가 Codex에 열려 있는지 확인
- Codex Automations에서 `Complete Watchdog weekly report`, `Complete Watchdog portfolio reports`, hourly news 자동화가 `ACTIVE`인지 확인
- Windows 작업 스케줄러가 필요하면 `python -m portfolio_watchdog install-schedule` 재실행

위클리 완성 리포트와 08/12/18 포트폴리오 리포트의 최종 Markdown 문안은 Codex 자동화가 작성합니다. 작성된 Markdown은 `complete-report` 명령으로 PDF 렌더링, 텔레그램 전송, 선택적 대시보드 동기화까지 한 번에 처리합니다. Windows 작업 스케줄러는 매시간 뉴스 체크와 08:00, 12:00, 18:00, 22:00 원장 동기화를 담당합니다.

## 로컬 투자 원장

`sync-ledger`는 기존 JSON 평가 이력을 SQLite로 가져온 뒤 Upbit/KIS 조회 전용 API에서 거래 이력을 수집하고, 현재 평가 스냅샷·보유수량 대사·TWR 성과를 계산합니다. 결과 v2 payload는 기본적으로 `snapshots/dashboard_v2_latest.json`에 저장되며, `--sync-dashboard`를 지정하면 개인정보 검사를 거쳐 Vercel 대시보드에도 업로드합니다.

기본 SQLite 위치는 `snapshots/watchdog.db`입니다. `.env`의 `WATCHDOG_LEDGER_PATH`를 설정하면 YAML의 `ledger.path`보다 우선합니다. 수량, 평단, 거래 메모 등 민감한 원장 정보는 로컬 SQLite에만 저장합니다.

운영·백업·복구 절차는 [원장 운영 Runbook](docs/operations/ledger-runbook.md)을 따릅니다.

## 호스팅 대시보드

`dashboard/` 폴더에는 Vercel 배포용 Next.js 대시보드가 있습니다. 로그인은 단일 비밀번호와 보안 쿠키를 사용하고, Watchdog CLI는 요약 payload만 `/api/upload`로 업로드합니다. 클라우드에는 수량, 평단, 계좌 식별자, API 키를 올리지 않습니다.

대시보드는 Next.js 16 기준이라 로컬 빌드에는 Node.js 20.9 이상이 필요합니다.

대시보드 환경 변수:

```text
DASHBOARD_PASSWORD_HASH=sha256 비밀번호 해시
DASHBOARD_SESSION_SECRET=긴 랜덤 문자열
WATCHDOG_UPLOAD_TOKEN=Watchdog CLI와 같은 업로드 토큰
BLOB_READ_WRITE_TOKEN=Vercel Blob 토큰
```

Vercel에는 위 웹앱용 값만 입력합니다. `UPBIT_ACCESS_KEY`, `UPBIT_SECRET_KEY`, `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`, `KIS_ACCOUNT_PRODUCT_CODE`는 로컬 Watchdog 실행 환경의 `.env`에만 둡니다. 대시보드는 계좌 API를 직접 조회하지 않고, Watchdog이 API로 만든 최신 요약 JSON을 Vercel Blob에서 읽습니다.

Watchdog 쪽 `.env`에는 아래 값을 추가합니다.

```text
WATCHDOG_DASHBOARD_UPLOAD_URL=https://<your-dashboard-domain>/api/upload
WATCHDOG_UPLOAD_TOKEN=위와 같은 업로드 토큰
```

비밀번호 해시는 대시보드 폴더에서 아래처럼 만들 수 있습니다.

```powershell
node -e "console.log(require('crypto').createHash('sha256').update('원하는비밀번호').digest('hex'))"
```

## 뉴스 기반 잠재 리스크

리스크 화면은 기존 수치 기반 위험과 별도로 최근 72시간 뉴스에서 발견한 잠재 리스크를 표시합니다. 자동 RSS 분석은 OpenAI API를 호출하지 않으며 별도 API 비용이 발생하지 않습니다. Codex 심층 분석은 정기 리포트 작성 또는 사용자가 요청한 시점에 별도 결과 파일을 생성해 병합합니다.

```powershell
python -m portfolio_watchdog collect-news-risks --sync-dashboard
python -m portfolio_watchdog merge-news-risks --path snapshots/codex_news_risk.json --sync-dashboard
python -m portfolio_watchdog sync-news-risks --path snapshots/news_risk_latest.json
python -m portfolio_watchdog install-schedule
```

뉴스 RSS 수집과 자산 API 동기화는 독립적으로 실패 처리됩니다. 뉴스 수집 실패가 자산 현황 표시를 막지 않고, 자산 API 실패가 기존 뉴스 리스크 파일을 삭제하지 않습니다. 클라우드에는 요약된 리스크만 Private Blob `dashboard/news-risk-latest.json`에 저장하며 뉴스 원문, 수량, 평단, 계좌 식별자, API 키는 업로드하지 않습니다.

상세 운영·복구 절차는 [뉴스 리스크 운영 Runbook](docs/operations/news-risk-runbook.md)을 참고합니다. 뉴스 리스크는 확인 우선순위를 설명하는 관찰 항목이며 매수·매도 추천이 아닙니다.

## 리포트 정확성 원칙

- 현재 자산 현황은 실행 시점 Upbit/KIS/가격 API 평가값을 기준으로 합니다.
- v1 대시보드의 종목 수익률은 매입가 대비 누계 평가손익률입니다.
- 로컬 v2 성과 요약의 누적·당월 수익률은 외부 입출금 영향을 제거한 TWR입니다.
- 대사 실패, fallback 평가, 정확한 경계 평가값이 없는 입출금 구간은 `provisional`로 표시합니다.
- 알 수 없는 사실은 `확인 불가`로 표시합니다.
- Codex의 해석이나 예상은 `Codex 해석` 또는 `Codex 추정`으로 명시합니다.
- PDF와 텔레그램 캡션은 같은 구조화 JSON을 기준으로 생성하며, 전송 전 총자산/자산군 합계/비중/변화율을 검증합니다.
