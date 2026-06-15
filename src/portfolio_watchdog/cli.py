import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .app import PortfolioWatchdogApp
from .config import load_config, load_env
from .runtime_paths import apply_env_base_paths, apply_runtime_base_paths, resolve_runtime_paths, resolve_setup_paths
from .scheduler import install_windows_schedule
from .setup_wizard import run_setup_wizard

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portfolio Watchdog")
    parser.add_argument("command", choices=["setup", "run", "check-news", "weekly-report", "weekly-source", "portfolio-source", "render-report-pdf", "send-report-document", "send-message-file", "complete-report", "sync-dashboard", "sync-report", "sync-opinions", "collect-news-risks", "merge-news-risks", "sync-news-risks", "send-sample-reports", "install-schedule", "check-config", "send-test-alert", "sync-ledger", "add-cash-flow", "performance-summary"])
    parser.add_argument("--config", default=None, help="설정 파일 경로")
    parser.add_argument("--env", default=None, help="환경 변수 파일 경로")
    parser.add_argument("--path", default=None, help="리포트/메시지/대시보드 원본 파일 경로")
    parser.add_argument("--output", default=None, help="render-report-pdf/complete-report에서 생성할 PDF 파일 경로")
    parser.add_argument("--sync-dashboard", action="store_true", help="complete-report 실행 후 대시보드를 동기화")
    parser.add_argument("--amount", type=float, default=None)
    parser.add_argument("--occurred-at", default=None)
    parser.add_argument("--memo", default=None)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "setup":
        run_setup_wizard(resolve_setup_paths(args.config, args.env), install_schedule_func=install_windows_schedule)
        return
    if args.command == "install-schedule":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        install_windows_schedule()
        logger.info("Windows 작업 스케줄러 등록을 완료했습니다.")
        return
    if args.command in {"render-report-pdf", "send-report-document", "send-message-file", "complete-report", "sync-dashboard", "sync-report", "sync-opinions", "merge-news-risks", "sync-news-risks"} and not args.path:
        parser.error(f"{args.command}에는 --path가 필요합니다.")

    runtime_paths = resolve_runtime_paths(args.config, args.env)
    try:
        env = apply_env_base_paths(load_env(Path(runtime_paths.env_path)), runtime_paths.settings_root)
        config = apply_runtime_base_paths(load_config(Path(runtime_paths.config_path)), runtime_paths.settings_root)
    except Exception as exc:
        logger.exception("설정 로드 실패")
        raise SystemExit(1) from exc

    app = PortfolioWatchdogApp(config=config, env=env, use_llm_news=args.command in {"run", "check-news", "weekly-report", "send-sample-reports"})
    if args.command == "run":
        app.run()
    elif args.command == "check-news":
        app.run_news_check()
    elif args.command == "weekly-report":
        app.run_weekly_report()
    elif args.command == "weekly-source":
        app.create_weekly_report_source()
    elif args.command == "portfolio-source":
        app.create_portfolio_report_source()
    elif args.command == "render-report-pdf":
        try:
            app.render_report_pdf(Path(args.path), Path(args.output) if args.output else None)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.command == "send-report-document":
        try:
            app.send_report_document(Path(args.path))
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.command == "send-message-file":
        try:
            app.send_message_file(Path(args.path))
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.command == "complete-report":
        try:
            app.complete_report(Path(args.path), Path(args.output) if args.output else None, sync_dashboard=args.sync_dashboard)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.command == "sync-dashboard":
        try:
            app.sync_dashboard(Path(args.path))
        except (FileNotFoundError, ValueError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.command == "sync-report":
        try:
            app.sync_report(Path(args.path))
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.command == "sync-opinions":
        try:
            app.sync_opinions(Path(args.path))
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.command == "collect-news-risks":
        try:
            app.collect_news_risks(Path(args.output) if args.output else None, sync_dashboard=args.sync_dashboard)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.command == "merge-news-risks":
        try:
            app.merge_news_risks(
                Path(args.path),
                Path(args.output) if args.output else None,
                sync_dashboard=args.sync_dashboard,
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.command == "sync-news-risks":
        try:
            app.sync_news_risks(Path(args.path))
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc
    elif args.command == "send-sample-reports":
        app.send_sample_reports()
    elif args.command == "check-config":
        app.check_config()
    elif args.command == "send-test-alert":
        app.send_test_alert()
    elif args.command in {"sync-ledger", "add-cash-flow", "performance-summary"}:
        try:
            if args.command == "sync-ledger":
                result = (
                    app.sync_ledger(sync_dashboard=True)
                    if args.sync_dashboard
                    else app.sync_ledger()
                )
            elif args.command == "performance-summary":
                result = app.performance_summary()
            else:
                result = app.add_cash_flow(
                    _required_amount(args.amount),
                    _parse_occurred_at(args.occurred_at),
                    _required_memo(args.memo),
                )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        except Exception as exc:
            logger.error("%s", exc)
            raise SystemExit(1) from exc


def _required_amount(value: float | None) -> float:
    if value is None:
        raise ValueError("add-cash-flow requires --amount")
    return value


def _required_memo(value: str | None) -> str:
    if value is None or not value.strip():
        raise ValueError("add-cash-flow requires a non-empty --memo")
    return value


def _parse_occurred_at(value: str | None) -> datetime:
    if value is None:
        raise ValueError("add-cash-flow requires --occurred-at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("--occurred-at must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
