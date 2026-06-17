from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict

from .cloud_contract import assert_cloud_safe


_IMPORTANCE = {"low", "medium", "high"}
_ASSET_GROUPS = {"isa", "coin", "cash"}


def build_economic_calendar_payload(source: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(source, dict):
        raise ValueError("economic calendar must be a JSON object")
    assert_cloud_safe(source)
    if source.get("schema_version") != "codex_economic_calendar_v1":
        raise ValueError("schema_version must be codex_economic_calendar_v1")
    for key in ("generated_at", "source"):
        _require_text(source, key)
    _require_datetime(source, "generated_at")
    if source.get("timezone") != "Asia/Seoul":
        raise ValueError("timezone must be Asia/Seoul")
    events = source.get("events")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    for event in events:
        _validate_event(event)

    payload = deepcopy(source)
    payload["schema_version"] = "dashboard_calendar_v1"
    assert_cloud_safe(payload)
    return payload


def _validate_event(event: Any) -> None:
    if not isinstance(event, dict):
        raise ValueError("each calendar event must be an object")
    for key in (
        "id",
        "title",
        "starts_at",
        "country",
        "category",
        "expected_impact",
        "watch_note",
    ):
        _require_text(event, key)
    _require_datetime(event, "starts_at")
    _require_choice(event, "importance", _IMPORTANCE)
    groups = event.get("asset_groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("asset_groups must contain at least one group")
    for group in groups:
        if group not in _ASSET_GROUPS:
            raise ValueError(f"asset_groups must only contain {sorted(_ASSET_GROUPS)}")
    if event.get("source_url") is not None and not isinstance(event.get("source_url"), str):
        raise ValueError("source_url must be a string or null")


def _require_text(value: Dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return item


def _require_choice(value: Dict[str, Any], key: str, choices: set[str]) -> None:
    if value.get(key) not in choices:
        raise ValueError(f"{key} must be one of {sorted(choices)}")


def _require_datetime(value: Dict[str, Any], key: str) -> None:
    text = _require_text(value, key)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{key} must be an ISO datetime") from None
