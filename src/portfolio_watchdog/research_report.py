from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict

from .cloud_contract import assert_cloud_safe


_REPORT_KINDS = {"portfolio", "weekly"}
_STANCES = {"positive", "neutral", "cautious"}
_ACTIONS = {"buy", "sell", "observe"}
_TONES = {"positive", "neutral", "negative"}


def build_research_report_payload(source: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(source, dict):
        raise ValueError("research report must be a JSON object")
    assert_cloud_safe(source)
    if source.get("schema_version") != "dashboard_report_v2":
        raise ValueError("schema_version must be dashboard_report_v2")
    if source.get("document_status") != "final":
        raise ValueError("dashboard_report_v2 must be a final report")
    for key in ("report_id", "generated_at", "title", "subtitle", "conclusion"):
        _require_text(source, key)
    _require_datetime(source, "generated_at")
    _require_choice(source, "report_kind", _REPORT_KINDS)
    _require_choice(source, "stance", _STANCES)
    _require_text_list(source, "executive_summary")
    _require_text_list(source, "risk_watchlist")
    _validate_summary(source.get("summary"))
    _validate_key_metrics(source.get("key_metrics"))
    _validate_thesis(source.get("investment_thesis"))
    _validate_asset_views(source.get("asset_views"))
    _validate_scenarios(source.get("scenarios"))
    if not isinstance(source.get("appendix"), dict):
        raise ValueError("appendix must be an object")

    payload = deepcopy(source)
    assert_cloud_safe(payload)
    return payload


def _validate_summary(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("summary must be an object")
    for key in ("total_value_krw", "change_krw"):
        if not _number(value.get(key)):
            raise ValueError(f"summary.{key} must be a finite number")
    if value.get("change_pct") is not None and not _number(value.get("change_pct")):
        raise ValueError("summary.change_pct must be a finite number or null")
    if not isinstance(value.get("validation_valid"), bool):
        raise ValueError("summary.validation_valid must be a boolean")


def _validate_key_metrics(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("key_metrics must contain at least one item")
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each key metric must be an object")
        for key in ("label", "value", "context"):
            _require_text(item, key)
        _require_choice(item, "tone", _TONES)


def _validate_thesis(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("investment_thesis must be an object")
    for key in ("headline", "body"):
        _require_text(value, key)
    for key in ("facts", "interpretations", "estimates"):
        _require_text_list(value, key)


def _validate_asset_views(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("asset_views must contain at least one item")
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each asset view must be an object")
        for key in ("symbol", "name", "thesis"):
            _require_text(item, key)
        _require_choice(item, "action", _ACTIONS)
        _require_text_list(item, "catalysts")
        _require_text_list(item, "risks")


def _validate_scenarios(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("scenarios must contain at least one item")
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("each scenario must be an object")
        for key in ("name", "probability", "trigger", "impact", "response"):
            _require_text(item, key)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_text(value: Dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return item


def _require_text_list(value: Dict[str, Any], key: str) -> None:
    items = value.get(key)
    if not isinstance(items, list) or not items or not all(
        isinstance(item, str) and item.strip() for item in items
    ):
        raise ValueError(f"{key} must contain non-empty strings")


def _require_choice(value: Dict[str, Any], key: str, choices: set[str]) -> None:
    if value.get(key) not in choices:
        raise ValueError(f"{key} must be one of {sorted(choices)}")


def _require_datetime(value: Dict[str, Any], key: str) -> None:
    text = _require_text(value, key)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{key} must be an ISO datetime") from None
