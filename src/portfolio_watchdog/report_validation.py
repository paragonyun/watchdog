from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ValidationResult:
    valid: bool
    issues: List[str]


def validate_report_payload(payload: Dict[str, Any]) -> ValidationResult:
    issues: List[str] = []
    current = payload.get("current_portfolio") or {}
    total = _as_float(current.get("total_value_krw"))
    groups = current.get("asset_groups") or {}
    assets = current.get("assets") or []

    group_sum = sum(_as_float(groups.get(key)) for key in ("coin", "equity", "cash"))
    if total <= 0:
        issues.append("총자산이 0원 이하입니다.")
    elif abs(total - group_sum) > max(1.0, total * 0.001):
        issues.append(f"총자산과 자산군 합계가 일치하지 않습니다: total={total:.2f}, groups={group_sum:.2f}")

    asset_sum = sum(_as_float(item.get("value_krw")) for item in assets)
    if total > 0 and abs(total - asset_sum) > max(1.0, total * 0.001):
        issues.append(f"총자산과 종목별 평가액 합계가 일치하지 않습니다: total={total:.2f}, assets={asset_sum:.2f}")

    weight_sum = sum(_as_float(item.get("weight_percent")) for item in assets)
    if assets and abs(weight_sum - 100.0) > 0.35:
        issues.append(f"종목별 비중 합계가 100% 근처가 아닙니다: weight_sum={weight_sum:.4f}")

    trend = payload.get("trend") or {}
    first = _as_float(trend.get("start_total_krw"))
    latest = _as_float(trend.get("latest_total_krw"))
    change = trend.get("change_krw")
    change_pct = trend.get("change_pct")
    if first > 0 and latest > 0 and change is not None:
        expected_change = latest - first
        if abs(_as_float(change) - expected_change) > max(1.0, latest * 0.001):
            issues.append("기간 변화액 계산이 시작값/현재값과 일치하지 않습니다.")
    if first > 0 and latest > 0 and change_pct is not None:
        expected_pct = (latest - first) / first * 100
        if abs(_as_float(change_pct) - expected_pct) > 0.05:
            issues.append("기간 변화율 계산이 시작값/현재값과 일치하지 않습니다.")

    for item in payload.get("news_impacts") or []:
        title = str(item.get("title") or "")
        impact = str(item.get("impact") or "")
        score = _optional_float(item.get("impact_score"))
        if score is not None and not -3 <= score <= 3:
            issues.append(f"뉴스 영향 강도가 범위를 벗어났습니다: {title}")
        if impact == "긍정" and score is not None and score < 0:
            issues.append(f"긍정 뉴스인데 음수 영향 강도가 설정되었습니다: {title}")
        if impact == "부정" and score is not None and score > 0:
            issues.append(f"부정 뉴스인데 양수 영향 강도가 설정되었습니다: {title}")

    return ValidationResult(valid=not issues, issues=issues)


def require_valid_report_payload(payload: Dict[str, Any]) -> None:
    result = validate_report_payload(payload)
    if not result.valid:
        raise ValueError("리포트 숫자 검증 실패: " + " / ".join(result.issues))


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return _as_float(value)
