from abc import ABC, abstractmethod
from typing import Any, Dict


class SnapshotRepository(ABC):
    @abstractmethod
    def load(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def save(self, snapshot: Dict[str, Any]) -> None:
        raise NotImplementedError
