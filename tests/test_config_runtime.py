from pathlib import Path

from portfolio_watchdog.config import load_config, load_env
from portfolio_watchdog.runtime_paths import (
    apply_env_base_paths,
    apply_runtime_base_paths,
    resolve_runtime_paths,
)


def test_load_config_and_env(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=x\n", encoding="utf-8")
    assert load_env(env_path)["TELEGRAM_BOT_TOKEN"] == "x"
    config = load_config(Path("config/config.yaml"))
    assert config.assets
    apply_runtime_base_paths(config, tmp_path)
    assert str(tmp_path) in config.snapshot.path


def test_runtime_path_explicit_config() -> None:
    paths = resolve_runtime_paths("config/config.yaml", ".env")
    assert paths.config_path == Path("config/config.yaml")
    assert paths.env_path == Path(".env")


def test_runtime_paths_resolve_ledger_and_env_override_from_settings_root(
    tmp_path,
) -> None:
    config = load_config(Path("config/config.yaml"))
    config.ledger.path = "configured/ledger.db"

    apply_runtime_base_paths(config, tmp_path)
    env = apply_env_base_paths(
        {"WATCHDOG_LEDGER_PATH": "override/watchdog.db"}, tmp_path
    )

    assert config.ledger.path == str(tmp_path / "configured" / "ledger.db")
    assert env["WATCHDOG_LEDGER_PATH"] == str(tmp_path / "override" / "watchdog.db")
