# Portfolio Watchdog

개인 포트폴리오를 주기적으로 조회하고 텔레그램으로 자산 현황, 뉴스 체크, 위클리 리포트 자료를 보내는 Windows 중심 도구입니다.

## 주요 명령

```powershell
python -m portfolio_watchdog setup
python -m portfolio_watchdog check-config
python -m portfolio_watchdog run
python -m portfolio_watchdog check-news
python -m portfolio_watchdog weekly-report
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
