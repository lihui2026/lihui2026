"""UI abstraction for future extensions (Web/Desktop)."""
from abc import ABC, abstractmethod
from typing import Any, Callable


class UIBackend(ABC):
    @abstractmethod
    def run(self) -> None:
        ...

    @abstractmethod
    def on_message(self, callback: Callable[[Any], None]) -> None:
        ...

    @abstractmethod
    def send_input(self, text: str) -> None:
        ...
