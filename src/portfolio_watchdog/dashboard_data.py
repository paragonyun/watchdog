from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

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


def upload_dashboard_payload(payload: Dict[str, Any], endpoint: Optional[str], token: Optional[str]) -> Dict[str, Any]:
    if not endpoint:
        raise ValueError("WATCHDOG_DASHBOARD_UPLOAD_URL 환경 변수가 필요합니다.")
    if not token:
        raise ValueError("WATCHDOG_UPLOAD_TOKEN 환경 변수가 필요합니다.")
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
    }


def _provider_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "provider": str(item.get("provider") or "unknown"),
        "used_fallback": bool(item.get("used_fallback")),
    }


def _optional_number(value: Any) -> Optional[float]:
    return None if value is None else _number(value)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
