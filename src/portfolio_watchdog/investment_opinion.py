from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict

from .cloud_contract import assert_cloud_safe


_ACTIONS = {"buy", "sell", "observe"}
_CONFIDENCE = {"low", "medium", "high"}


def build_investment_opinion_payload(source: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(source, dict):
        raise ValueError("Codex investment opinion must be a JSON object")
    assert_cloud_safe(source)
    if source.get("schema_version") != "codex_investment_opinion_v1":
        raise ValueError("schema_version must be codex_investment_opinion_v1")
    _require_text(source, "opinion_id")
    _require_datetime(source, "generated_at")
    _require_choice(source, "portfolio_posture", _ACTIONS)
    _require_text(source, "summary")
    _require_text(source, "disclaimer")
    items = source.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("items must contain at least one Codex opinion")
    for item in items:
        _validate_item(item)

    payload = deepcopy(source)
    payload["schema_version"] = "dashboard_opinion_v1"
    assert_cloud_safe(payload)
    return payload


def _validate_item(item: Any) -> None:
    if not isinstance(item, dict):
        raise ValueError("each opinion item must be an object")
    for key in ("id", "symbol", "name", "thesis", "suggested_position_note"):
        _require_text(item, key)
    _require_choice(item, "action", _ACTIONS)
    _require_choice(item, "confidence", _CONFIDENCE)
    for key in (
        "evidence",
        "counter_evidence",
        "catalysts",
        "invalidation_conditions",
    ):
        _require_text_list(item, key)
    sources = item.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources must contain at least one source")
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("each source must be an object")
        _require_text(source, "label")
        if source.get("url") is not None and not isinstance(source.get("url"), str):
            raise ValueError("source url must be a string or null")


def _require_text(value: Dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return item


def _require_text_list(value: Dict[str, Any], key: str) -> None:
    items = value.get(key)
    if not isinstance(items, list) or not all(
        isinstance(item, str) and item.strip() for item in items
    ):
        raise ValueError(f"{key} must be a list of non-empty strings")


def _require_choice(value: Dict[str, Any], key: str, choices: set[str]) -> None:
    if value.get(key) not in choices:
        raise ValueError(f"{key} must be one of {sorted(choices)}")


def _require_datetime(value: Dict[str, Any], key: str) -> None:
    text = _require_text(value, key)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{key} must be an ISO datetime") from None
