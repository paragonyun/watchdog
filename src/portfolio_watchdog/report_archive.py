from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List

from .cloud_contract import assert_cloud_safe
from .dashboard_data import build_dashboard_payload


_REPORT_NAME = re.compile(
    r"(weekly|portfolio)_report_(?:final|source)_(\d{8})_(\d{4})",
    re.IGNORECASE,
)
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_BRACKET_HEADING = re.compile(r"^\[(.+?)\]\s*$")
_SENSITIVE_TEXT = re.compile(
    r"\b(?:quantity|current_quantity|average_buy_price_krw|account_no|"
    r"account_product_code|order_id|order_no|uuid|access_key|api_key|"
    r"app_key|secret_key|app_secret|raw_response|raw_api_response)\b|"
    r"수량\s*:|평단\s*:|평균\s*매수가\s*:|계좌\s*번호\s*:|API\s*키\s*:|비밀\s*키\s*:",
    re.IGNORECASE,
)


def build_report_archive_payload(
    report_text: str,
    report_payload: Dict[str, Any],
    filename: str,
) -> Dict[str, Any]:
    if not isinstance(report_text, str) or not report_text.strip():
        raise ValueError("리포트 본문이 비어 있습니다.")
    if len(report_text) > 200_000:
        raise ValueError("리포트 본문은 200,000자를 초과할 수 없습니다.")
    if _SENSITIVE_TEXT.search(report_text):
        raise ValueError("리포트 본문에 민감 정보 표현이 포함되어 있습니다.")

    dashboard = build_dashboard_payload(report_payload)
    report_kind = str(report_payload.get("report_kind") or "portfolio")
    generated_at = str(report_payload.get("generated_at") or "")
    archive = {
        "schema_version": "dashboard_report_v1",
        "report_id": _report_id(filename, report_kind, generated_at),
        "generated_at": generated_at,
        "report_kind": report_kind,
        "title": _report_title(report_kind),
        "document_status": "final" if "_final_" in filename.lower() else "source",
        "summary": {
            "total_value_krw": dashboard["total_value_krw"],
            "change_krw": dashboard["trend"]["change_krw"],
            "change_pct": dashboard["trend"]["change_pct"],
            "validation_valid": bool(
                (report_payload.get("validation") or {}).get("valid")
            ),
        },
        "sections": _parse_sections(report_text),
        "appendix": {
            "asset_groups": dashboard["asset_groups"],
            "assets": dashboard["assets"],
            "provider_status": dashboard["provider_status"],
            "validation_issues": [
                str(issue)
                for issue in (report_payload.get("validation") or {}).get("issues") or []
            ],
        },
    }
    assert_cloud_safe(archive)
    return archive


def _report_id(filename: str, report_kind: str, generated_at: str) -> str:
    match = _REPORT_NAME.search(filename)
    if match:
        kind, date, time = match.groups()
        return f"{kind.lower()}-{date}-{time}"
    try:
        generated = datetime.fromisoformat(generated_at)
    except (TypeError, ValueError):
        raise ValueError("리포트 ID 생성을 위한 generated_at이 필요합니다.") from None
    safe_kind = "weekly" if report_kind == "weekly" else "portfolio"
    return f"{safe_kind}-{generated:%Y%m%d-%H%M}"


def _report_title(report_kind: str) -> str:
    return "주간 포트폴리오 리포트" if report_kind == "weekly" else "포트폴리오 리포트"


def _parse_sections(report_text: str) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for raw_line in report_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = _heading(line)
        if heading:
            current = {"title": heading, "lines": []}
            sections.append(current)
            continue
        if current is None:
            current = {"title": "개요", "lines": []}
            sections.append(current)
        normalized = re.sub(r"^[-*]\s+", "", line)
        current["lines"].append(normalized)
    return [section for section in sections if section["lines"]]


def _heading(line: str) -> str | None:
    for pattern in (_MARKDOWN_HEADING, _BRACKET_HEADING):
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return None
