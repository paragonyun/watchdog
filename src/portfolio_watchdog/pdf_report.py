import html
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .report_data import load_report_payload_for_path
from .report_validation import require_valid_report_payload

_GROUP_LABELS = {"coin": "코인", "equity": "ISA", "cash": "현금"}
_GROUP_COLORS = {"coin": colors.HexColor("#2563EB"), "equity": colors.HexColor("#059669"), "cash": colors.HexColor("#D97706")}
_NEUTRAL = colors.HexColor("#6B7280")
_DARK = colors.HexColor("#111827")
_LIGHT_BG = colors.HexColor("#F3F4F6")
_DRAWING_FONT = "Helvetica"
_DRAWING_BOLD_FONT = "Helvetica-Bold"


def render_weekly_report_pdf(markdown_path: Path, history: Dict[str, Any], output_path: Optional[Path] = None) -> Path:
    report_path = Path(markdown_path)
    if not report_path.exists():
        raise FileNotFoundError(f"완성 리포트 파일을 찾을 수 없습니다: {report_path}")
    if not report_path.is_file():
        raise ValueError(f"완성 리포트 경로가 파일이 아닙니다: {report_path}")

    regular_font, bold_font = _register_fonts()
    styles = _build_styles(regular_font, bold_font)
    report_text = report_path.read_text(encoding="utf-8")
    payload = load_report_payload_for_path(report_path)
    if payload is not None:
        require_valid_report_payload(payload)
    snapshots = (payload or {}).get("snapshots") or _recent_snapshots(history.get("portfolio_snapshots", []))
    latest = (payload or {}).get("current_portfolio") or (snapshots[-1] if snapshots else {})
    news_items = (payload or {}).get("news_items") or history.get("news_items", [])
    output = output_path or report_path.with_suffix(".pdf")
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=15 * mm,
        title="Portfolio Watchdog Weekly Report",
    )
    story: List[Any] = []
    story.extend(_build_cover(styles, latest, report_text, _report_title(payload)))
    if payload is not None:
        story.extend(_build_payload_dashboard(styles, payload))
    else:
        story.extend(_build_dashboard(styles, snapshots, news_items))
    story.append(PageBreak())
    story.extend(_markdown_to_flowables(report_text, styles))

    def footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont(regular_font, 8)
        canvas.setFillColor(_NEUTRAL)
        canvas.drawString(document.leftMargin, 8 * mm, "Portfolio Watchdog")
        canvas.drawRightString(A4[0] - document.rightMargin, 8 * mm, f"{document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output


def _register_fonts() -> Tuple[str, str]:
    global _DRAWING_FONT, _DRAWING_BOLD_FONT
    regular_path = Path(r"C:\Windows\Fonts\malgun.ttf")
    bold_path = Path(r"C:\Windows\Fonts\malgunbd.ttf")
    try:
        if "MalgunGothic" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("MalgunGothic", str(regular_path)))
        if "MalgunGothic-Bold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("MalgunGothic-Bold", str(bold_path)))
        _DRAWING_FONT = "MalgunGothic"
        _DRAWING_BOLD_FONT = "MalgunGothic-Bold"
        return "MalgunGothic", "MalgunGothic-Bold"
    except Exception:
        _DRAWING_FONT = "Helvetica"
        _DRAWING_BOLD_FONT = "Helvetica-Bold"
        return "Helvetica", "Helvetica-Bold"


def _build_styles(regular_font: str, bold_font: str):
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("KTitle", parent=styles["Title"], fontName=bold_font, fontSize=22, leading=28, textColor=_DARK, spaceAfter=8),
        "subtitle": ParagraphStyle("KSubtitle", parent=styles["BodyText"], fontName=regular_font, fontSize=9, leading=13, textColor=_NEUTRAL, spaceAfter=8),
        "section": ParagraphStyle("KSection", parent=styles["Heading2"], fontName=bold_font, fontSize=13, leading=17, textColor=_DARK, spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("KBody", parent=styles["BodyText"], fontName=regular_font, fontSize=9.3, leading=14, textColor=_DARK, spaceAfter=5),
        "bullet": ParagraphStyle("KBullet", parent=styles["BodyText"], fontName=regular_font, fontSize=9.1, leading=13, leftIndent=12, firstLineIndent=0, spaceAfter=3),
        "small": ParagraphStyle("KSmall", parent=styles["BodyText"], fontName=regular_font, fontSize=7.8, leading=10, textColor=_NEUTRAL),
        "kpi_label": ParagraphStyle("KKpiLabel", parent=styles["BodyText"], fontName=regular_font, fontSize=7.6, leading=9, textColor=_NEUTRAL),
        "kpi_value": ParagraphStyle("KKpiValue", parent=styles["BodyText"], fontName=bold_font, fontSize=12, leading=15, textColor=_DARK),
    }


def _report_title(payload: Optional[Dict[str, Any]]) -> str:
    if not payload:
        return "Portfolio Watchdog 위클리 리포트"
    return "Portfolio Watchdog 위클리 리포트" if payload.get("report_kind") == "weekly" else "Portfolio Watchdog 포트폴리오 리포트"


def _build_cover(styles, latest: Dict[str, Any], report_text: str, title: str = "Portfolio Watchdog 위클리 리포트") -> List[Any]:
    generated_at = _format_datetime(latest.get("captured_at")) or datetime.now().strftime("%Y-%m-%d %H:%M")
    return [
        Paragraph(html.escape(title), styles["title"]),
        Paragraph(f"전문 분석 보고서 | 기준 시각 {html.escape(generated_at)}", styles["subtitle"]),
        Spacer(1, 4 * mm),
        Paragraph(_extract_summary(report_text), styles["body"]),
        Spacer(1, 6 * mm),
        _kpi_table(latest, styles),
        Spacer(1, 8 * mm),
    ]


def _build_payload_dashboard(styles, payload: Dict[str, Any]) -> List[Any]:
    current = payload["current_portfolio"]
    snapshots = list(payload.get("snapshots") or [])
    if not snapshots or snapshots[-1].get("captured_at") != current.get("captured_at"):
        snapshots.append(current)
    flowables: List[Any] = [
        _notice_box(payload, styles),
        Spacer(1, 5 * mm),
        Paragraph("1. 핵심 요약", styles["section"]),
        _summary_table(payload, styles),
        Spacer(1, 6 * mm),
        Paragraph("2. 자산 배분 현황", styles["section"]),
        _allocation_chart(current),
        Spacer(1, 4 * mm),
        _group_table(current, styles),
        PageBreak(),
        Paragraph("3. 평가액 추세 및 자산군별 변화", styles["section"]),
    ]
    if len(snapshots) >= 2:
        flowables.extend([_trend_chart(snapshots), Spacer(1, 4 * mm), _group_change_table(snapshots[0], current, styles)])
    else:
        flowables.append(Paragraph("추세 판단에 필요한 스냅샷이 부족합니다.", styles["body"]))
    flowables.extend(
        [
            Spacer(1, 6 * mm),
            Paragraph("4. 자산군별 단기/중장기 영향", styles["section"]),
            _asset_group_effect_table(styles),
            PageBreak(),
            Paragraph("5. 현재 종목별 현황", styles["section"]),
            _asset_table(current.get("assets", []), styles),
            Spacer(1, 6 * mm),
            Paragraph("6. 뉴스 영향 해석", styles["section"]),
            _news_impact_table(payload.get("news_impacts", []), styles),
            PageBreak(),
            Paragraph("7. 리스크 변화 진단", styles["section"]),
            _risk_table(payload, styles),
            Spacer(1, 6 * mm),
            Paragraph("8. 금융기관 전망 요약", styles["section"]),
            _institution_view_table(styles),
            Spacer(1, 6 * mm),
            Paragraph("9. 다음 체크포인트", styles["section"]),
            _checkpoint_table(styles),
        ]
    )
    return flowables


def _build_dashboard(styles, snapshots: List[Dict[str, Any]], news_items: List[Dict[str, Any]]) -> List[Any]:
    flowables: List[Any] = [Paragraph("대시보드", styles["section"])]
    if len(snapshots) >= 2:
        flowables.append(_trend_chart(snapshots))
        flowables.append(Spacer(1, 5 * mm))
        charts = Table(
            [[_allocation_chart(snapshots[-1]), _group_change_chart(snapshots[0], snapshots[-1])]],
            colWidths=[82 * mm, 82 * mm],
        )
        charts.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        flowables.append(charts)
    else:
        flowables.append(Paragraph("아직 차트를 만들 만큼 주간 스냅샷이 충분하지 않습니다.", styles["body"]))
    flowables.append(Spacer(1, 6 * mm))
    flowables.append(Paragraph("현재 자산별 현황", styles["section"]))
    flowables.append(_asset_table((snapshots[-1] if snapshots else {}).get("assets", []), styles))
    flowables.append(Spacer(1, 5 * mm))
    flowables.append(Paragraph("뉴스 영향 분포", styles["section"]))
    flowables.append(_news_table(news_items[-20:], styles))
    return flowables


def _notice_box(payload: Dict[str, Any], styles) -> Table:
    provider_lines = []
    for item in payload.get("provider_status") or []:
        if item.get("used_fallback"):
            provider_lines.append(f"{item.get('provider')}: API 조회 실패, fallback 사용")
    provider_note = " / ".join(provider_lines) if provider_lines else "API 조회 실패 로그 없음"
    text = (
        "주의: 현재 현황은 실행 시점 API 평가값 기준이며, 추세는 히스토리 스냅샷 기준입니다. "
        "입출금 보정은 적용하지 않습니다. 확인되지 않은 사실은 확인 불가로 표시합니다. "
        f"API 상태: {provider_note}."
    )
    table = Table([[Paragraph(html.escape(text), styles["small"])]], colWidths=[160 * mm])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF4FF")), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#B7C7E6")), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return table


def _summary_table(payload: Dict[str, Any], styles) -> Table:
    trend = payload.get("trend") or {}
    validation = payload.get("validation") or {}
    rows = [
        [Paragraph("구분", styles["small"]), Paragraph("판단", styles["small"])],
        [Paragraph("기간 변화", styles["small"]), Paragraph(html.escape(f"{_format_krw(_as_float(trend.get('change_krw')))} / {_format_optional_pct(trend.get('change_pct'))}"), styles["small"])],
        [Paragraph("검증", styles["small"]), Paragraph("숫자 검증 통과" if validation.get("valid") else html.escape("검증 이슈: " + ", ".join(validation.get("issues", []))), styles["small"])],
        [Paragraph("해석 기준", styles["small"]), Paragraph("뉴스 영향 강도는 Codex 해석이며, 확인 불가 내용은 사실처럼 쓰지 않습니다.", styles["small"])],
    ]
    table = Table(rows, colWidths=[36 * mm, 124 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _group_table(current: Dict[str, Any], styles) -> Table:
    labels = {"coin": "코인", "equity": "ISA", "cash": "현금"}
    total = _as_float(current.get("total_value_krw"))
    rows = [[Paragraph("자산군", styles["small"]), Paragraph("평가액", styles["small"]), Paragraph("비중", styles["small"]), Paragraph("해석", styles["small"])]]
    descriptions = {
        "coin": "Codex 해석: 수익 회복 가능성과 단기 변동성이 동시에 큰 구간입니다.",
        "equity": "확인된 사실: 포트폴리오 중심축이며 금리와 미국 주식 흐름에 민감합니다.",
        "cash": "확인된 사실: 단기 변동성 완충 및 의사결정 여력입니다.",
    }
    for key, label in labels.items():
        value = _as_float((current.get("asset_groups") or {}).get(key))
        rows.append([Paragraph(label, styles["small"]), Paragraph(_format_krw(value), styles["small"]), Paragraph(_format_optional_pct(value / total * 100 if total else 0), styles["small"]), Paragraph(descriptions[key], styles["small"])])
    table = Table(rows, colWidths=[24 * mm, 34 * mm, 24 * mm, 78 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _group_change_table(first: Dict[str, Any], latest: Dict[str, Any], styles) -> Table:
    labels = {"coin": "코인", "equity": "ISA", "cash": "현금"}
    rows = [[Paragraph("자산군", styles["small"]), Paragraph("시작", styles["small"]), Paragraph("현재", styles["small"]), Paragraph("변화율", styles["small"]), Paragraph("요약", styles["small"])]]
    for key, label in labels.items():
        start = _as_float((first.get("asset_groups") or {}).get(key))
        current = _as_float((latest.get("asset_groups") or {}).get(key))
        pct = _pct_change(start, current)
        summary = "상승" if (pct or 0) > 0.05 else "하락" if (pct or 0) < -0.05 else "변화 제한"
        rows.append([Paragraph(label, styles["small"]), Paragraph(_format_krw(start), styles["small"]), Paragraph(_format_krw(current), styles["small"]), Paragraph(_format_optional_pct(pct), styles["small"]), Paragraph(summary, styles["small"])])
    table = Table(rows, colWidths=[24 * mm, 34 * mm, 34 * mm, 24 * mm, 44 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _asset_group_effect_table(styles) -> Table:
    rows = [[Paragraph("자산군", styles["small"]), Paragraph("단기 영향", styles["small"]), Paragraph("중장기 영향", styles["small"]), Paragraph("관찰 포인트", styles["small"])]]
    rows.extend(
        [
            [Paragraph("코인", styles["small"]), Paragraph("Codex 해석: 규제/유동성 뉴스에 따라 변동성이 커질 수 있습니다.", styles["small"]), Paragraph("확인된 사실: BTC/ETH 등 보유 자산의 수익률과 뉴스 흐름을 계속 확인해야 합니다.", styles["small"]), Paragraph("BTC ETF/기관 자금, ETH 상대강도, 알트코인 유동성", styles["small"])],
            [Paragraph("ISA", styles["small"]), Paragraph("Codex 해석: 금리와 미국 주식 뉴스가 단기 민감도를 높입니다.", styles["small"]), Paragraph("확인된 사실: ISA 비중이 크므로 전체 포트폴리오 방향성에 영향이 큽니다.", styles["small"]), Paragraph("미국 금리, 달러, 나스닥 밸류에이션, 금 가격", styles["small"])],
            [Paragraph("현금", styles["small"]), Paragraph("확인된 사실: 평가액 변동은 없으며 완충 역할입니다.", styles["small"]), Paragraph("Codex 해석: 변동성 확대 구간에서 의사결정 여력을 제공합니다.", styles["small"]), Paragraph("현금 비중, 생활/목표자금 안정성", styles["small"])],
        ]
    )
    table = Table(rows, colWidths=[21 * mm, 46 * mm, 58 * mm, 35 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _news_impact_table(items: List[Dict[str, Any]], styles) -> Table:
    rows = [[Paragraph("뉴스/테마", styles["small"]), Paragraph("방향", styles["small"]), Paragraph("강도", styles["small"]), Paragraph("관련 자산", styles["small"]), Paragraph("포트폴리오 해석", styles["small"])]]
    for item in items[:7]:
        related = ", ".join(item.get("related_assets") or []) or "시장 전반"
        link_text = str(item.get("title") or "")[:48]
        if item.get("url"):
            title_para = Paragraph(f'<a href="{html.escape(str(item["url"]), quote=True)}">{html.escape(link_text)}</a>', styles["small"])
        else:
            title_para = Paragraph(html.escape(link_text), styles["small"])
        rows.append(
            [
                title_para,
                Paragraph(html.escape(str(item.get("impact") or "중립")), styles["small"]),
                Paragraph(html.escape(f"{item.get('impact_score', 0):+} / Codex 해석"), styles["small"]),
                Paragraph(html.escape(related), styles["small"]),
                Paragraph(html.escape(str(item.get("reason") or "확인 불가")), styles["small"]),
            ]
        )
    if len(rows) == 1:
        rows.append([Paragraph("확인된 주요 뉴스 없음", styles["small"]), Paragraph("-", styles["small"]), Paragraph("0", styles["small"]), Paragraph("-", styles["small"]), Paragraph("확인 불가", styles["small"])])
    table = Table(rows, colWidths=[48 * mm, 18 * mm, 24 * mm, 34 * mm, 36 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _risk_table(payload: Dict[str, Any], styles) -> Table:
    current = payload["current_portfolio"]
    total = _as_float(current.get("total_value_krw"))
    coin = _as_float((current.get("asset_groups") or {}).get("coin"))
    cash = _as_float((current.get("asset_groups") or {}).get("cash"))
    rows = [
        [Paragraph("항목", styles["small"]), Paragraph("현재 판단", styles["small"]), Paragraph("의미", styles["small"])],
        [Paragraph("코인 비중", styles["small"]), Paragraph(_format_optional_pct(coin / total * 100 if total else 0), styles["small"]), Paragraph("Codex 해석: 단기 변동성은 크지만 전체 자산을 압도하는 수준은 아닙니다.", styles["small"])],
        [Paragraph("현금 비중", styles["small"]), Paragraph(_format_optional_pct(cash / total * 100 if total else 0), styles["small"]), Paragraph("확인된 사실: 변동성 완충 역할을 합니다.", styles["small"])],
        [Paragraph("검증 상태", styles["small"]), Paragraph("통과" if (payload.get("validation") or {}).get("valid") else "실패", styles["small"]), Paragraph("PDF와 캡션은 같은 원천 JSON 기준으로 작성됩니다.", styles["small"])],
    ]
    table = Table(rows, colWidths=[30 * mm, 34 * mm, 96 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _institution_view_table(styles) -> Table:
    rows = [
        [Paragraph("항목", styles["small"]), Paragraph("내용", styles["small"])],
        [Paragraph("공개 전망", styles["small"]), Paragraph("Codex automation 실행 시점에 웹에서 공개 출처를 확인해 작성합니다.", styles["small"])],
        [Paragraph("확인 불가 처리", styles["small"]), Paragraph("출처명/날짜/링크를 확인하지 못하면 '확인된 공개 전망 없음'으로 표시합니다.", styles["small"])],
        [Paragraph("주의", styles["small"]), Paragraph("전망 요약은 투자 지시가 아니라 관찰 자료입니다.", styles["small"])],
    ]
    table = Table(rows, colWidths=[34 * mm, 126 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _checkpoint_table(styles) -> Table:
    rows = [[Paragraph("체크포인트", styles["small"])]]
    points = [
        "총자산 변화가 자산군 합계와 계속 일치하는지 확인",
        "금리/달러 뉴스가 ISA와 금/국채 자산에 미치는 영향 확인",
        "BTC 호재가 ETH와 알트코인으로 확산되는지 확인",
        "대표 뉴스의 후속 보도와 가격 반응이 같은 방향인지 확인",
        "API 조회 실패 또는 fallback 사용 여부 확인",
    ]
    rows.extend([[Paragraph(point, styles["small"])] for point in points])
    table = Table(rows, colWidths=[160 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _kpi_table(latest: Dict[str, Any], styles) -> Table:
    groups = latest.get("asset_groups", {}) or {}
    total = _as_float(latest.get("total_value_krw"))
    cells = [
        _kpi_cell("총 자산", _format_krw(total), styles),
        _kpi_cell("코인", _format_krw(_as_float(groups.get("coin"))), styles),
        _kpi_cell("ISA", _format_krw(_as_float(groups.get("equity"))), styles),
        _kpi_cell("현금", _format_krw(_as_float(groups.get("cash"))), styles),
    ]
    table = Table([cells], colWidths=[40 * mm, 40 * mm, 40 * mm, 40 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_BG),
                ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _kpi_cell(label: str, value: str, styles) -> List[Paragraph]:
    return [Paragraph(html.escape(label), styles["kpi_label"]), Paragraph(html.escape(value), styles["kpi_value"])]


def _trend_chart(snapshots: List[Dict[str, Any]]) -> Drawing:
    data = snapshots[-12:]
    values = [_as_float(item.get("total_value_krw")) for item in data]
    width, height = 500, 170
    left, right, top, bottom = 38, 18, 22, 32
    chart_w, chart_h = width - left - right, height - top - bottom
    low, high = min(values), max(values)
    if low == high:
        low *= 0.98
        high *= 1.02
    drawing = Drawing(width, height)
    drawing.add(String(0, height - 10, "총 자산 추세", fontName=_DRAWING_BOLD_FONT, fontSize=9, fillColor=_DARK))
    drawing.add(Line(left, top + chart_h, left + chart_w, top + chart_h, strokeColor=colors.HexColor("#E5E7EB")))
    drawing.add(Line(left, top, left, top + chart_h, strokeColor=colors.HexColor("#D1D5DB")))
    points = []
    for index, value in enumerate(values):
        x = left + (chart_w * index / max(len(values) - 1, 1))
        y = top + ((value - low) / (high - low) * chart_h)
        points.extend([x, y])
        drawing.add(Circle(x, y, 2.2, fillColor=colors.HexColor("#2563EB"), strokeColor=colors.HexColor("#2563EB")))
    drawing.add(PolyLine(points, strokeColor=colors.HexColor("#2563EB"), strokeWidth=1.5))
    drawing.add(String(left, 8, _format_datetime(data[0].get("captured_at"))[:10], fontName=_DRAWING_FONT, fontSize=7, fillColor=_NEUTRAL))
    drawing.add(String(left + chart_w - 50, 8, _format_datetime(data[-1].get("captured_at"))[:10], fontName=_DRAWING_FONT, fontSize=7, fillColor=_NEUTRAL))
    drawing.add(String(left + chart_w - 86, height - 10, f"{_format_krw(values[-1])}", fontName=_DRAWING_FONT, fontSize=8, fillColor=_NEUTRAL))
    return drawing


def _allocation_chart(latest: Dict[str, Any]) -> Drawing:
    groups = latest.get("asset_groups", {}) or {}
    total = sum(_as_float(groups.get(key)) for key in _GROUP_LABELS) or 1.0
    drawing = Drawing(230, 135)
    drawing.add(String(0, 124, "자산군 비중", fontName=_DRAWING_BOLD_FONT, fontSize=9, fillColor=_DARK))
    x, y, bar_w, bar_h = 0, 92, 220, 18
    cursor = x
    for key, label in _GROUP_LABELS.items():
        value = _as_float(groups.get(key))
        width = bar_w * value / total
        drawing.add(Rect(cursor, y, width, bar_h, fillColor=_GROUP_COLORS[key], strokeColor=None))
        cursor += width
    label_y = 68
    for key, label in _GROUP_LABELS.items():
        value = _as_float(groups.get(key))
        pct = value / total * 100
        drawing.add(Rect(0, label_y - 2, 8, 8, fillColor=_GROUP_COLORS[key], strokeColor=None))
        drawing.add(String(12, label_y, f"{label} {pct:.1f}% / {_format_krw(value)}", fontName=_DRAWING_FONT, fontSize=7.5, fillColor=_DARK))
        label_y -= 18
    return drawing


def _group_change_chart(first: Dict[str, Any], latest: Dict[str, Any]) -> Drawing:
    first_groups = first.get("asset_groups", {}) or {}
    latest_groups = latest.get("asset_groups", {}) or {}
    changes = {key: _pct_change(_as_float(first_groups.get(key)), _as_float(latest_groups.get(key))) or 0.0 for key in _GROUP_LABELS}
    max_abs = max([abs(value) for value in changes.values()] + [1.0])
    drawing = Drawing(230, 135)
    drawing.add(String(0, 124, "자산군 주간 변화율", fontName=_DRAWING_BOLD_FONT, fontSize=9, fillColor=_DARK))
    base_y, gap = 84, 26
    axis_x, max_w = 88, 105
    drawing.add(Line(axis_x, 20, axis_x, 105, strokeColor=colors.HexColor("#D1D5DB")))
    for index, (key, label) in enumerate(_GROUP_LABELS.items()):
        y = base_y - index * gap
        value = changes[key]
        width = abs(value) / max_abs * max_w
        color = colors.HexColor("#059669") if value >= 0 else colors.HexColor("#DC2626")
        x = axis_x if value >= 0 else axis_x - width
        drawing.add(String(0, y + 3, label, fontName=_DRAWING_FONT, fontSize=7.5, fillColor=_DARK))
        drawing.add(Rect(x, y, width, 10, fillColor=color, strokeColor=None))
        drawing.add(String(axis_x + max_w + 4, y + 2, f"{value:+.2f}%", fontName=_DRAWING_FONT, fontSize=7, fillColor=_NEUTRAL))
    return drawing


def _asset_table(assets: List[Dict[str, Any]], styles) -> Table:
    rows = [[Paragraph("자산", styles["small"]), Paragraph("평가액", styles["small"]), Paragraph("비중", styles["small"]), Paragraph("수익률", styles["small"])]]
    for item in sorted(assets, key=lambda row: _as_float(row.get("value_krw")), reverse=True)[:12]:
        rows.append(
            [
                Paragraph(html.escape(str(item.get("name") or item.get("symbol") or "-")), styles["small"]),
                Paragraph(html.escape(_format_krw(_as_float(item.get("value_krw")))), styles["small"]),
                Paragraph(html.escape(f"{_as_float(item.get('weight_percent')):.2f}%"), styles["small"]),
                Paragraph(html.escape(_format_optional_pct(item.get("profit_loss_rate_percent"))), styles["small"]),
            ]
        )
    table = Table(rows, colWidths=[58 * mm, 35 * mm, 27 * mm, 35 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _news_table(news_items: List[Dict[str, Any]], styles) -> Table:
    counts = {"긍정": 0, "부정": 0, "중립": 0}
    for item in news_items:
        impact = str(item.get("impact") or "중립")
        counts[impact if impact in counts else "중립"] += 1
    rows = [
        [Paragraph("긍정", styles["small"]), Paragraph(str(counts["긍정"]), styles["small"])],
        [Paragraph("부정", styles["small"]), Paragraph(str(counts["부정"]), styles["small"])],
        [Paragraph("중립", styles["small"]), Paragraph(str(counts["중립"]), styles["small"])],
    ]
    table = Table(rows, colWidths=[40 * mm, 25 * mm])
    table.setStyle(_table_style())
    return table


def _table_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F9FAFB")),
            ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def _markdown_to_flowables(text: str, styles) -> List[Any]:
    flowables: List[Any] = [Paragraph("분석 본문", styles["section"])]
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flowables.append(Spacer(1, 2 * mm))
            continue
        if line.startswith("# "):
            flowables.append(Paragraph(_inline(line[2:]), styles["title"]))
        elif line.startswith("## "):
            flowables.append(Paragraph(_inline(line[3:]), styles["section"]))
        elif line.startswith("- "):
            flowables.append(Paragraph(_inline(line[2:]), styles["bullet"], bulletText="•"))
        elif re.match(r"^\d+\.\s+", line):
            number, body = line.split(".", 1)
            flowables.append(Paragraph(_inline(body.strip()), styles["bullet"], bulletText=f"{number}."))
        else:
            flowables.append(Paragraph(_inline(line), styles["body"]))
    return flowables


def _inline(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def _extract_summary(text: str) -> str:
    bullets: List[str] = []
    in_summary = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## 핵심 요약"):
            in_summary = True
            continue
        if in_summary and line.startswith("## "):
            break
        if in_summary and line.startswith("- "):
            bullets.append(line[2:])
        if len(bullets) >= 3:
            break
    return "<br/>".join(f"• {_inline(item)}" for item in bullets) if bullets else "자동 생성된 포트폴리오 주간 분석 보고서입니다."


def _recent_snapshots(items: List[Dict[str, Any]], days: int = 7) -> List[Dict[str, Any]]:
    parsed = [item for item in items if _parse_datetime(item.get("captured_at")) is not None]
    parsed.sort(key=lambda item: item.get("captured_at") or "")
    if not parsed:
        return []
    latest_dt = _parse_datetime(parsed[-1].get("captured_at")) or datetime.now()
    since = latest_dt - timedelta(days=days)
    return [item for item in parsed if (_parse_datetime(item.get("captured_at")) or since) >= since]


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_datetime(value: Any) -> str:
    parsed = _parse_datetime(value)
    return "" if parsed is None else f"{parsed:%Y-%m-%d %H:%M}"


def _pct_change(first: float, latest: float) -> Optional[float]:
    return None if first <= 0 else (latest - first) / first * 100


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_krw(value: float) -> str:
    return f"{value:,.0f}원"


def _format_optional_pct(value: Any) -> str:
    if value is None:
        return "-"
    return f"{_as_float(value):+.2f}%"
