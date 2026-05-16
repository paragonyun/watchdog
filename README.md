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

위클리 완성 리포트와 08/12/18 포트폴리오 리포트는 Codex 자동화가 PDF로 생성해 텔레그램으로 보냅니다. Windows 작업 스케줄러는 매시간 뉴스 체크만 담당합니다.

## 리포트 정확성 원칙

- 현재 자산 현황은 실행 시점 Upbit/KIS/가격 API 평가값을 기준으로 합니다.
- 평가액 추세는 히스토리 스냅샷 기준이며, 입출금 보정은 적용하지 않습니다.
- 알 수 없는 사실은 `확인 불가`로 표시합니다.
- Codex의 해석이나 예상은 `Codex 해석` 또는 `Codex 추정`으로 명시합니다.
- PDF와 텔레그램 캡션은 같은 구조화 JSON을 기준으로 생성하며, 전송 전 총자산/자산군 합계/비중/변화율을 검증합니다.
