from pathlib import Path

import portfolio_watchdog.notifiers.telegram as telegram_module
from portfolio_watchdog.notifiers.telegram import TelegramNotifier


def test_telegram_message_payload(monkeypatch) -> None:
    calls = []

    class Response:
        def raise_for_status(self): return None
        def json(self): return {"ok": True, "result": {"message_id": 1}}

    monkeypatch.setattr(telegram_module.requests, "post", lambda *args, **kwargs: calls.append((args, kwargs)) or Response())
    notifier = TelegramNotifier("token", "chat")
    notifier.notify("<b>hello</b>")
    assert calls[0][1]["data"]["parse_mode"] == "HTML"
    assert calls[0][1]["data"]["disable_web_page_preview"] is True


def test_telegram_document_payload(monkeypatch, tmp_path) -> None:
    calls = []

    class Response:
        def raise_for_status(self): return None
        def json(self): return {"ok": True, "result": {"message_id": 2}}

    path = tmp_path / "weekly.txt"
    path.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(telegram_module.requests, "post", lambda *args, **kwargs: calls.append((args, kwargs)) or Response())
    TelegramNotifier("token", "chat").notify_document(path, "<b>caption</b>")
    assert calls[0][0][0].endswith("/sendDocument")
    assert "document" in calls[0][1]["files"]
