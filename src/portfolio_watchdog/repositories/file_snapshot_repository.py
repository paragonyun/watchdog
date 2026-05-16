import json
import os
from pathlib import Path
from typing import Any, Dict

from .base import SnapshotRepository


class FileSnapshotRepository(SnapshotRepository):
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"alert_keys": []}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {"alert_keys": []}
        except Exception:
            return {"alert_keys": []}

    def save(self, snapshot: Dict[str, Any]) -> None:
        tmp_path = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(snapshot, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        finally:
            tmp_path.unlink(missing_ok=True)
