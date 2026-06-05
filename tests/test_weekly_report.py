from datetime import datetime, timedelta

import pytest

import portfolio_watchdog.app as app_module
from portfolio_watchdog.app import PortfolioWatchdogApp
from portfolio_watchdog.config import AlertConfig, AppConfig, AssetConfig, NewsConfig, PriceProviderConfig, SnapshotConfig, TelegramConfig
from portfolio_watchdog.models import AssetEvaluation, PortfolioEvaluation
from portfolio_watchdog.providers.rss_news_provider import RssNewsProvider
from portfolio_watchdog.report_data import ReportArtifact
from portfolio_watchdog.weekly_report import build_weekly_report_source, build_weekly_report_telegram_summary


def test_weekly_report_includes_trend(tmp_path) -> None:
    now = datetime(2026, 5, 8, 12, 0)
    portfolio = PortfolioEvaluation(
        assets=[AssetEvaluation(symbol="BTC", name="Bitcoin", asset_type="coin", target_weight=1, current_quantity=1, manual_value_krw=None, current_value_krw=1100, current_weight=1, profit_loss_rate_pct=10)],
        total_value_krw=1100,
    )
    history = {"portfolio_snapshots": [{"captured_at": (now - timedelta(days=6)).isoformat(), "total_value_krw": 1000, "asset_groups": {"coin": 1000}}, {"captured_at": now.isoformat(), "total_value_krw": 1100, "asset_groups": {"coin": 1100}}], "news_items": []}
    source = build_weekly_report_source(portfolio, history, generated_at=now)
    summary = build_weekly_report_telegram_summary(portfolio, history, tmp_path / "weekly.txt", generated_at=now)
    assert "변화: 100원 (+10.00%)" in source
    assert "첨부된 txt 파일" in summary


def test_weekly_source_creates_file_without_notification(monkeypatch, tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    calls = []

    def fake_write(source: str, payload: dict, prefix: str, directory: str = "reports", now=None):
        path = tmp_path / "weekly_report_source_test.txt"
        data_path = tmp_path / "weekly_report_source_test.json"
        path.write_text(source, encoding="utf-8")
        data_path.write_text("{}", encoding="utf-8")
        return ReportArtifact(path, data_path)

    monkeypatch.setattr(app_module, "write_report_artifact", fake_write)
    monkeypatch.setattr(watchdog, "_notify_file_safe", lambda *args: calls.append(args))

    path = watchdog.create_weekly_report_source()

    assert path.exists()
    assert "현재 포트폴리오" in path.read_text(encoding="utf-8")
    assert calls == []


def test_portfolio_source_creates_file_without_notification(monkeypatch, tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    calls = []

    def fake_write(source: str, payload: dict, prefix: str, directory: str = "reports", now=None):
        path = tmp_path / "portfolio_report_source_test.txt"
        data_path = tmp_path / "portfolio_report_source_test.json"
        path.write_text(source, encoding="utf-8")
        data_path.write_text("{}", encoding="utf-8")
        return ReportArtifact(path, data_path)

    monkeypatch.setattr(app_module, "write_report_artifact", fake_write)
    monkeypatch.setattr(watchdog, "_notify_file_safe", lambda *args: calls.append(args))

    path = watchdog.create_portfolio_report_source()

    assert path.exists()
    assert "포트폴리오 전문 PDF" in path.read_text(encoding="utf-8")
    assert calls == []


def test_send_report_document_notifies_existing_file(monkeypatch, tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    path = tmp_path / "weekly_report_final_20260516_2010.md"
    path.write_text("# 위클리 리포트\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(watchdog, "_notify_file_safe", lambda *args: calls.append(args))

    watchdog.send_report_document(path)

    assert calls[0][0] == path
    assert "Portfolio Watchdog 리포트" in calls[0][1]


def test_complete_report_renders_sends_and_syncs(monkeypatch, tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    markdown = tmp_path / "portfolio_report_final_20260605_0800.md"
    output = tmp_path / "portfolio_report_final_20260605_0800.pdf"
    markdown.write_text("# 포트폴리오 리포트\n", encoding="utf-8")
    calls = []

    def fake_render(path, output_path=None):
        calls.append(("render", path, output_path))
        output.write_bytes(b"%PDF")
        return output

    monkeypatch.setattr(watchdog, "render_report_pdf", fake_render)
    monkeypatch.setattr(watchdog, "send_report_document", lambda path: calls.append(("send", path)))
    monkeypatch.setattr(watchdog, "sync_dashboard", lambda path: calls.append(("sync", path)))

    result = watchdog.complete_report(markdown, output, sync_dashboard=True)

    assert result == output
    assert calls == [
        ("render", markdown, output),
        ("send", output),
        ("sync", markdown),
    ]


def test_sync_dashboard_uploads_summary_payload(monkeypatch, tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={"WATCHDOG_DASHBOARD_UPLOAD_URL": "https://example.com/api/upload", "WATCHDOG_UPLOAD_TOKEN": "token"})
    source = tmp_path / "portfolio_report_source_20260605_0800.json"
    source.write_text(
        '{"report_kind":"portfolio","generated_at":"2026-06-05T08:00:00","current_portfolio":{"total_value_krw":1000,"asset_groups":{"coin":200,"equity":700,"cash":100},"assets":[]},"trend":{},"news_impacts":[],"provider_status":[]}',
        encoding="utf-8",
    )
    calls = []

    monkeypatch.setattr(app_module, "upload_dashboard_payload", lambda payload, endpoint, token: calls.append((payload, endpoint, token)) or {"ok": True})

    payload = watchdog.sync_dashboard(source)

    assert payload["schema_version"] == "dashboard_payload_v1"
    assert calls[0][1:] == ("https://example.com/api/upload", "token")


def test_send_report_document_missing_file_error(tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    missing = tmp_path / "missing.md"

    with pytest.raises(FileNotFoundError, match="리포트 파일을 찾을 수 없습니다"):
        watchdog.send_report_document(missing)


def test_send_message_file_notifies_file_content(monkeypatch, tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})
    path = tmp_path / "hourly_news_codex_20260516_1307.html"
    path.write_text("<b>뉴스 요약</b>\n- 금리 확인", encoding="utf-8")
    calls = []
    monkeypatch.setattr(watchdog, "_notify_safe", lambda message: calls.append(message))

    watchdog.send_message_file(path)

    assert calls == ["<b>뉴스 요약</b>\n- 금리 확인"]


def test_send_message_file_missing_file_error(tmp_path) -> None:
    watchdog = PortfolioWatchdogApp(_app_config(tmp_path), env={})

    with pytest.raises(FileNotFoundError, match="메시지 파일을 찾을 수 없습니다"):
        watchdog.send_message_file(tmp_path / "missing.html")


def test_app_can_disable_llm_news_for_codex_automation(tmp_path) -> None:
    config = _app_config(tmp_path)
    config.news.provider_type = "rss"
    config.news.llm_enabled = True

    watchdog = PortfolioWatchdogApp(config, env={"OPENAI_API_KEY": "secret"}, use_llm_news=False)

    assert isinstance(watchdog.news_provider, RssNewsProvider)


def _app_config(tmp_path) -> AppConfig:
    return AppConfig(
        assets=[
            AssetConfig(
                symbol="CASH",
                name="현금",
                asset_type="cash",
                target_weight=1.0,
                manual_value_krw=1000,
            )
        ],
        price_provider=PriceProviderConfig(provider_type="mock"),
        alert_settings=AlertConfig(),
        telegram=TelegramConfig(enabled=False),
        snapshot=SnapshotConfig(path=str(tmp_path / "state.json"), history_path=str(tmp_path / "history.json")),
        news=NewsConfig(provider_type="noop"),
    )
