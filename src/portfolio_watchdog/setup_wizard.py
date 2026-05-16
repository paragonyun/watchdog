import sys
from pathlib import Path
from shutil import copyfile
from typing import Callable, Dict, Optional

from .runtime_paths import RuntimePaths, get_executable_root

InputFunc = Callable[[str], str]
OutputFunc = Callable[[str], None]

_ENV_ORDER = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "UPBIT_ACCESS_KEY",
    "UPBIT_SECRET_KEY",
    "KIS_APP_KEY",
    "KIS_APP_SECRET",
    "KIS_ACCOUNT_NO",
    "KIS_ACCOUNT_PRODUCT_CODE",
    "KIS_ENV",
    "KIS_TOKEN_CACHE_PATH",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_API_BASE",
]


def run_setup_wizard(
    paths: RuntimePaths,
    input_func: InputFunc = input,
    output_func: OutputFunc = print,
    install_schedule_func: Optional[Callable[[], None]] = None,
) -> None:
    output_func("Portfolio Watchdog 초기 설정을 시작합니다.")
    paths.settings_root.mkdir(parents=True, exist_ok=True)
    paths.config_path.parent.mkdir(parents=True, exist_ok=True)

    if not paths.config_path.exists():
        copyfile(find_config_template(), paths.config_path)
        output_func(f"설정 파일을 생성했습니다: {paths.config_path}")
    else:
        output_func(f"기존 설정 파일을 유지합니다: {paths.config_path}")

    if paths.env_path.exists() and not _confirm(
        input_func,
        ".env 파일이 이미 있습니다. 다시 작성할까요?",
        default=False,
    ):
        output_func(f"기존 환경변수 파일을 유지합니다: {paths.env_path}")
    else:
        write_env_file(paths.env_path, collect_env_values(input_func))
        output_func(f"환경변수 파일을 저장했습니다: {paths.env_path}")

    if install_schedule_func and _confirm(
        input_func,
        "Windows 작업 스케줄러에 자동 실행을 등록할까요?",
        default=False,
    ):
        install_schedule_func()
        output_func("Windows 작업 스케줄러 등록을 완료했습니다.")


def collect_env_values(input_func: InputFunc = input) -> Dict[str, str]:
    values = {
        "TELEGRAM_BOT_TOKEN": _ask(input_func, "Telegram Bot Token"),
        "TELEGRAM_CHAT_ID": _ask(input_func, "Telegram Chat ID"),
        "UPBIT_ACCESS_KEY": "",
        "UPBIT_SECRET_KEY": "",
        "KIS_APP_KEY": "",
        "KIS_APP_SECRET": "",
        "KIS_ACCOUNT_NO": "",
        "KIS_ACCOUNT_PRODUCT_CODE": "",
        "KIS_ENV": "real",
        "KIS_TOKEN_CACHE_PATH": "snapshots/kis_token.json",
        "OPENAI_API_KEY": "",
        "OPENAI_MODEL": "gpt-4o-mini",
        "OPENAI_API_BASE": "https://api.openai.com/v1",
    }

    if _confirm(input_func, "Upbit 자산조회 API를 입력할까요?", default=False):
        values["UPBIT_ACCESS_KEY"] = _ask(input_func, "Upbit Access Key")
        values["UPBIT_SECRET_KEY"] = _ask(input_func, "Upbit Secret Key")

    if _confirm(input_func, "한국투자증권 ISA 조회 API를 입력할까요?", default=False):
        values["KIS_APP_KEY"] = _ask(input_func, "KIS App Key")
        values["KIS_APP_SECRET"] = _ask(input_func, "KIS App Secret")
        values["KIS_ACCOUNT_NO"] = _ask(input_func, "KIS 계좌번호 앞 8자리")
        values["KIS_ACCOUNT_PRODUCT_CODE"] = _ask(input_func, "KIS 계좌 상품코드 2자리")

    if _confirm(
        input_func,
        "OpenAI API 키를 입력할까요? 비워두면 비용 없는 규칙 기반 뉴스 분석을 사용합니다.",
        default=False,
    ):
        values["OPENAI_API_KEY"] = _ask(input_func, "OpenAI API Key")
        values["OPENAI_MODEL"] = _ask(input_func, "OpenAI Model", default="gpt-4o-mini") or "gpt-4o-mini"

    return values


def write_env_file(path: Path, values: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={values.get(key, '')}" for key in _ENV_ORDER]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def find_config_template() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", get_executable_root()))
    candidates = [
        get_executable_root() / "config" / "config.example.yaml",
        bundle_root / "config" / "config.example.yaml",
        Path.cwd() / "config" / "config.example.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("config.example.yaml 템플릿을 찾을 수 없습니다.")


def _ask(input_func: InputFunc, label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input_func(f"{label}{suffix}: ").strip()
    return value or default


def _confirm(input_func: InputFunc, question: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    value = input_func(f"{question} ({suffix}): ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "예", "네"}
