from html import escape
from typing import List


def html_escape(value: object, quote: bool = False) -> str:
    return escape(str(value), quote=quote)


def split_message(message: str, limit: int = 3500) -> List[str]:
    if len(message) <= limit:
        return [message]
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for line in message.splitlines():
        line_len = len(line) + 1
        if current and current_len + line_len > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks
