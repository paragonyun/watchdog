import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import AppConfig

APP_DIR_NAME = "PortfolioWatchdog"


@dataclass
class RuntimePaths:
    config_path: Path
    env_path: Path
    settings_root: Path


def resolve_runtime_paths(config_arg: Optional[str] = None, env_arg: Optional[str] = None) -> RuntimePaths:
    if config_arg or env_arg:
        config_path = Path(config_arg or "config/config.yaml")
        env_path = Path(env_arg or ".env")
        return RuntimePaths(config_path=config_path, env_path=env_path, settings_root=_settings_root_for(config_path))
    adjacent = _paths_for_root(get_executable_root())
    if adjacent.config_path.exists():
        return adjacent
    appdata = _paths_for_root(get_appdata_root())
    if appdata.config_path.exists():
        return appdata
    return adjacent


def resolve_setup_paths(config_arg: Optional[str] = None, env_arg: Optional[str] = None) -> RuntimePaths:
    if config_arg or env_arg:
        config_path = Path(config_arg or "config/config.yaml")
        env_path = Path(env_arg or ".env")
        return RuntimePaths(config_path=config_path, env_path=env_path, settings_root=_settings_root_for(config_path))
    root = get_executable_root()
    return _paths_for_root(root if _is_writable_directory(root) else get_appdata_root())


def get_executable_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd().resolve()


def get_appdata_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home()) / APP_DIR_NAME


def apply_runtime_base_paths(config: AppConfig, settings_root: Path) -> AppConfig:
    config.snapshot.path = _absolute_if_relative(config.snapshot.path, settings_root)
    config.snapshot.history_path = _absolute_if_relative(config.snapshot.history_path, settings_root)
    config.news.snapshot_path = _absolute_if_relative(config.news.snapshot_path, settings_root)
    return config


def apply_env_base_paths(env: dict[str, str], settings_root: Path) -> dict[str, str]:
    value = env.get("KIS_TOKEN_CACHE_PATH")
    if value:
        env["KIS_TOKEN_CACHE_PATH"] = _absolute_if_relative(value, settings_root)
    return env


def _paths_for_root(root: Path) -> RuntimePaths:
    return RuntimePaths(config_path=root / "config" / "config.yaml", env_path=root / ".env", settings_root=root)


def _settings_root_for(config_path: Path) -> Path:
    path = config_path.resolve()
    return path.parent.parent if path.parent.name.lower() == "config" else path.parent


def _absolute_if_relative(value: str, settings_root: Path) -> str:
    path = Path(value)
    return str(path if path.is_absolute() else settings_root / path)


def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False
