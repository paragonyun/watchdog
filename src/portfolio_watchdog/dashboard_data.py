from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .cloud_contract import assert_cloud_safe
from .report_data import load_report_payload_for_path


def load_dashboard_source_payload(path: Path) -> Dict[str, Any]:
    report_path = Path(path)
    if not report_path.exists():
        raise FileNotFoundError(f"대시보드 동기화 원본을 찾을 수 없습니다: {report_path}")
    if report_path.suffix.lower() == ".json":
        import json

        return json.loads(report_path.read_text(encoding="utf-8"))
    payload = load_report_payload_for_path(report_path)
    if payload is None:
        raise ValueError(f"대시보드 payload JSON을 찾을 수 없습니다: {report_path}")
    return payload


def build_dashboard_payload(report_payload: Dict[str, Any]) -> Dict[str, Any]:
    current = report_payload.get("current_portfolio") or {}
    return {
        "schema_version": "dashboard_payload_v1",
        "generated_at": report_payload.get("generated_at"),
        "report_kind": report_payload.get("report_kind"),
        "total_value_krw": _number(current.get("total_value_krw")),
        "asset_groups": _asset_groups(current.get("asset_groups") or {}),
        "assets": [_asset_summary(item) for item in current.get("assets") or []],
        "trend": _trend_summary(report_payload.get("trend") or {}),
        "news_impacts": [_news_summary(item) for item in report_payload.get("news_impacts") or []],
        "provider_status": [_provider_summary(item) for item in report_payload.get("provider_status") or []],
    }


def build_dashboard_payload_v2(summary: Dict[str, Any]) -> Dict[str, Any]:
    data_freshness = summary.get("data_freshness") or {}
    performance = summary.get("performance") or {}
    generated_at = summary.get("generated_at")
    _validate_iso_datetime("generated_at", generated_at)
    payload = {
        "schema_version": "dashboard_payload_v2",
        "generated_at": generated_at,
        "total_value_krw": _v2_number(summary.get("total_value_krw")),
        "data_freshness": _allowed_fields(
            data_freshness,
            ("portfolio_status", "last_actual_at", "reconciliation_status"),
        ),
        "performance": _allowed_fields(
            performance,
            (
                "cumulative_twr_pct",
                "month_twr_pct",
                "benchmark_return_pct",
                "excess_return_pct",
                "max_drawdown_pct",
                "status",
            ),
            status_values={"confirmed", "provisional", "insufficient_data"},
        ),
        "asset_groups": [
            _asset_group_summary_v2(item)
            for item in _asset_group_items(summary.get("asset_groups") or [])
        ],
        "assets": [
            _asset_summary_v2(item) for item in summary.get("assets") or []
        ],
        "provider_status": [
            _provider_summary_v2(item)
            for item in summary.get("provider_status") or []
        ],
    }
    assert_cloud_safe(payload)
    return payload


def upload_dashboard_payload(payload: Dict[str, Any], endpoint: Optional[str], token: Optional[str]) -> Dict[str, Any]:
    if not endpoint:
        raise ValueError("WATCHDOG_DASHBOARD_UPLOAD_URL 환경 변수가 필요합니다.")
    if not token:
        raise ValueError("WATCHDOG_UPLOAD_TOKEN 환경 변수가 필요합니다.")
    assert_cloud_safe(payload)
    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"dashboard upload failed: {exc}") from exc
    try:
        data = response.json()
    except ValueError:
        return {"ok": True}
    return data if isinstance(data, dict) else {"ok": True}


def _asset_groups(groups: Dict[str, Any]) -> Dict[str, float]:
    return {key: _number(groups.get(key)) for key in ("coin", "equity", "cash")}


def _asset_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": str(item.get("symbol") or ""),
        "name": str(item.get("name") or item.get("symbol") or ""),
        "asset_type": str(item.get("asset_type") or ""),
        "value_krw": _number(item.get("value_krw")),
        "weight_percent": _number(item.get("weight_percent")),
        "profit_loss_rate_percent": _optional_number(item.get("profit_loss_rate_percent")),
        "price_source": str(item.get("price_source") or "unknown"),
    }


def _trend_summary(trend: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "start_at": trend.get("start_at"),
        "latest_at": trend.get("latest_at"),
        "start_total_krw": _number(trend.get("start_total_krw")),
        "latest_total_krw": _number(trend.get("latest_total_krw")),
        "change_krw": _number(trend.get("change_krw")),
        "change_pct": _optional_number(trend.get("change_pct")),
        "snapshot_count": int(_number(trend.get("snapshot_count"))),
    }


def _news_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": str(item.get("title") or ""),
        "impact": str(item.get("impact") or "중립"),
        "impact_score": int(_number(item.get("impact_score"))),
        "score_label": str(item.get("score_label") or "Codex 해석"),
        "related_assets": [str(symbol) for symbol in item.get("related_assets") or []],
        "reason": str(item.get("reason") or "확인 불가"),
        "why_it_matters": str(item.get("why_it_matters") or ""),
        "url": item.get("url"),
        "published_at": item.get("published_at"),
    }


def _provider_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "provider": str(item.get("provider") or "unknown"),
        "used_fallback": bool(item.get("used_fallback")),
    }


def _asset_group_items(groups: Any) -> List[Dict[str, Any]]:
    if isinstance(groups, list):
        return groups
    if isinstance(groups, dict):
        return [
            (
                {**value, "asset_group": asset_group}
                if isinstance(value, dict)
                else {"asset_group": asset_group, "value_krw": value}
            )
            for asset_group, value in groups.items()
        ]
    return []


def _asset_group_summary_v2(item: Dict[str, Any]) -> Dict[str, Any]:
    summary = _allowed_fields(
        item,
        (
            "asset_group",
            "value_krw",
            "weight_percent",
            "target_diff_percentage_points",
            "profit_loss_rate_percent",
            "cumulative_profit_loss_rate_percent",
        ),
    )
    if "asset_group" in summary:
        summary["asset_group"] = _v2_asset_group(summary["asset_group"])
    return summary


def _asset_summary_v2(item: Dict[str, Any]) -> Dict[str, Any]:
    summary = _allowed_fields(
        item,
        (
            "symbol",
            "name",
            "asset_type",
            "value_krw",
            "weight_percent",
            "target_diff_percentage_points",
            "profit_loss_rate_percent",
            "cumulative_profit_loss_rate_percent",
        ),
    )
    if "asset_type" in summary:
        summary["asset_type"] = _v2_asset_group(summary["asset_type"])
    return summary


def _provider_summary_v2(item: Dict[str, Any]) -> Dict[str, Any]:
    return _allowed_fields(
        item,
        ("provider", "status", "used_fallback", "last_actual_at"),
        status_values={
            "actual",
            "estimated",
            "stale",
            "fallback",
            "ok",
            "error",
            "failed",
            "unavailable",
            "partial",
        },
    )


def _allowed_fields(
    item: Dict[str, Any],
    fields: tuple[str, ...],
    status_values: set[str] | None = None,
) -> Dict[str, Any]:
    result = {}
    for field in fields:
        if field not in item:
            continue
        value = item[field]
        _validate_v2_field(field, value, status_values)
        result[field] = value
    return result


def _validate_v2_field(
    field: str, value: Any, status_values: set[str] | None = None
) -> None:
    if value is None:
        return
    enums = {
        "portfolio_status": {"actual", "estimated", "stale", "fallback"},
        "reconciliation_status": {"reconciled", "reconciliation_required"},
        "asset_group": {"isa", "equity", "coin", "cash"},
        "asset_type": {"isa", "equity", "coin", "cash"},
    }
    if field == "status":
        if (
            status_values is None
            or not isinstance(value, str)
            or value not in status_values
        ):
            raise ValueError("invalid dashboard v2 enum: status")
        return
    if field in enums:
        if not isinstance(value, str) or value not in enums[field]:
            raise ValueError(f"invalid dashboard v2 enum: {field}")
        return
    if field == "used_fallback":
        if type(value) is not bool:
            raise ValueError("dashboard v2 used_fallback must be a bool")
        return
    if field == "last_actual_at":
        _validate_iso_datetime(field, value)
        return
    if field in {
        "value_krw",
        "weight_percent",
        "target_diff_percentage_points",
        "profit_loss_rate_percent",
        "cumulative_profit_loss_rate_percent",
        "cumulative_twr_pct",
        "month_twr_pct",
        "benchmark_return_pct",
        "excess_return_pct",
        "max_drawdown_pct",
    }:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"dashboard v2 field must be a finite number: {field}")
        return
    if not isinstance(value, str):
        raise ValueError(f"dashboard v2 field must be a string: {field}")


def _v2_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("dashboard v2 total_value_krw must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("dashboard v2 total_value_krw must be finite")
    return number


def _validate_iso_datetime(field: str, value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError(f"dashboard v2 {field} must be an ISO datetime string")
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"dashboard v2 {field} must be an ISO datetime string"
        ) from error


def _v2_asset_group(value: Any) -> Any:
    return "isa" if value == "equity" else value


def _optional_number(value: Any) -> Optional[float]:
    return None if value is None else _number(value)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
