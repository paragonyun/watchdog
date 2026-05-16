from pathlib import Path

from portfolio_watchdog.config import load_config, load_env
from portfolio_watchdog.runtime_paths import apply_runtime_base_paths, resolve_runtime_paths


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
