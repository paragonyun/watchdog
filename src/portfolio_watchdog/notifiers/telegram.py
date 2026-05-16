import logging
from pathlib import Path
from typing import Dict, Optional

import requests

from .base import Notifier

logger = logging.getLogger(__name__)


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id
        self.url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.document_url = f"https://api.telegram.org/bot{self.token}/sendDocument"
        self.last_message_id: Optional[int] = None

    def notify(self, message: str) -> None:
        payload: Dict[str, str | bool] = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        response = requests.post(self.url, data=payload, timeout=10)
        self._handle_response(response, "Telegram notification sent")

    def notify_document(self, path: Path, caption: str = "") -> None:
        payload = {"chat_id": self.chat_id, "caption": caption, "parse_mode": "HTML"}
        with path.open("rb") as handle:
            response = requests.post(
                self.document_url,
                data=payload,
                files={"document": (path.name, handle)},
                timeout=20,
            )
        self._handle_response(response, f"Telegram document sent, path={path}")

    def _handle_response(self, response, log_message: str) -> None:
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description") or "Telegram API returned ok=false.")
        self.last_message_id = (data.get("result") or {}).get("message_id")
        logger.info("%s, message_id=%s", log_message, self.last_message_id)


def build_telegram_notifier(env: Dict[str, Optional[str]]) -> Optional[Notifier]:
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram config is missing: token/chat_id required.")
        return None
    return TelegramNotifier(token=token, chat_id=chat_id)
