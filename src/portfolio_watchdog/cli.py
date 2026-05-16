import argparse
import logging
from pathlib import Path

from .app import PortfolioWatchdogApp
from .config import load_config, load_env
from .runtime_paths import apply_env_base_paths, apply_runtime_base_paths, resolve_runtime_paths, resolve_setup_paths
from .scheduler import install_windows_schedule
from .setup_wizard import run_setup_wizard

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio Watchdog")
    parser.add_argument("command", choices=["setup", "run", "check-news", "weekly-report", "send-sample-reports", "install-schedule", "check-config", "send-test-alert"])
    parser.add_argument("--config", default=None, help="설정 파일 경로")
    parser.add_argument("--env", default=None, help="환경 변수 파일 경로")
    args = parser.parse_args()

    if args.command == "setup":
        run_setup_wizard(resolve_setup_paths(args.config, args.env), install_schedule_func=install_windows_schedule)
        return
    if args.command == "install-schedule":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        install_windows_schedule()
        logger.info("Windows 작업 스케줄러 등록을 완료했습니다.")
        return

    runtime_paths = resolve_runtime_paths(args.config, args.env)
    try:
        env = apply_env_base_paths(load_env(Path(runtime_paths.env_path)), runtime_paths.settings_root)
        config = apply_runtime_base_paths(load_config(Path(runtime_paths.config_path)), runtime_paths.settings_root)
    except Exception as exc:
        logger.exception("설정 로드 실패")
        raise SystemExit(1) from exc

    app = PortfolioWatchdogApp(config=config, env=env)
    if args.command == "run":
        app.run()
    elif args.command == "check-news":
        app.run_news_check()
    elif args.command == "weekly-report":
        app.run_weekly_report()
    elif args.command == "send-sample-reports":
        app.send_sample_reports()
    elif args.command == "check-config":
        app.check_config()
    elif args.command == "send-test-alert":
        app.send_test_alert()
